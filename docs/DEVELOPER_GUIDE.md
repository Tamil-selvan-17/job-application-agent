# Developer Guide

How this project is put together, how to run it locally, and how to extend it.

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async), Python 3.12 |
| Database | MongoDB (via motor, async driver) |
| Frontend | Plain HTML + Bootstrap 5 + vanilla JS (no build step, no framework) |
| AI | Ollama (local) or Gemini API - switchable via `.env` |
| Email | Mailjet / Brevo / SendGrid (HTTP APIs) or SMTP - switchable via `.env` |
| Scheduler | APScheduler (in-process, runs daily search + follow-up checks) |
| Deployment | Render (Blueprint via `render.yaml`) |

No authentication - this is a single-user personal tool by design.

## Project Structure

```
job-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, router registration, lifespan
│   │   ├── config/
│   │   │   └── env.py                # All environment variables (pydantic-settings)
│   │   ├── database/
│   │   │   └── mongo.py              # Motor client singleton
│   │   ├── models/                   # Pydantic request/response schemas
│   │   │   ├── config_model.py       # Job search config JSON shape
│   │   │   ├── resume_model.py
│   │   │   ├── cover_letter_model.py
│   │   │   └── job_model.py
│   │   ├── routers/                  # FastAPI route definitions (thin - delegate to services)
│   │   │   ├── config_router.py
│   │   │   ├── settings_router.py
│   │   │   ├── ai_router.py
│   │   │   ├── resume_router.py
│   │   │   ├── cover_letter_router.py
│   │   │   ├── job_router.py
│   │   │   ├── jobsearch_router.py
│   │   │   └── notifications_router.py
│   │   └── services/                 # Actual business logic lives here
│   │       ├── ai_provider.py        # Ollama/Gemini abstraction
│   │       ├── config_service.py     # Job search config CRUD (stored in Mongo)
│   │       ├── resume_parser.py      # PDF/DOCX text extraction
│   │       ├── resume_service.py
│   │       ├── cover_letter_service.py
│   │       ├── job_service.py        # Job CRUD, AI analysis, apply flows
│   │       ├── job_sources.py        # Remotive/Arbeitnow/Adzuna connectors
│   │       ├── job_search_service.py # Orchestrates search + all filtering
│   │       ├── job_matching.py       # Keyword/location/language/experience matchers
│   │       ├── email_service.py      # Custom relay/Mailjet/Brevo/SendGrid/SMTP senders
│   │       ├── excel_import_service.py  # Bulk job import from .xlsx (in-memory, never stored)
│   │       ├── runtime_settings_service.py  # Mongo-backed UI-switchable settings (e.g. Gemini model)
│   │       └── scheduler_service.py  # APScheduler daily jobs
│   ├── uploads/                      # Resume/cover-letter files land here
│   ├── requirements.txt
│   ├── .env.example
│   └── .python-version               # Pinned to 3.12.6 - see Gotchas below
├── frontend/
│   ├── index.html                    # Single page, tab-based UI
│   ├── css/style.css
│   └── js/app.js                     # All frontend logic, no build step
├── docker/
│   ├── docker-compose.yml            # Mongo, Redis, Qdrant, Ollama, backend
│   └── Dockerfile.backend
├── render.yaml                       # Render Blueprint
└── docs/                             # You are here
```

## Architecture Pattern: Routers vs Services

Every router is intentionally thin - it validates input, calls a service function, and maps `ValueError` to an HTTP error:

```python
@router.post("/{job_id}/analyze")
async def analyze_job(job_id: str, resume_id: str | None = Query(None)):
    try:
        return await job_service.analyze_job(job_id, resume_id=resume_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

All actual logic (Mongo queries, AI calls, file handling) lives in `services/`. When adding a feature, write the service function first, then a thin router wrapper.

## Key Abstractions (and why they exist)

### AI Provider (`services/ai_provider.py`)
Every AI-powered feature calls `get_ai_provider()` and then `.generate(prompt, system)` - never talks to Ollama or Gemini directly. Reads `AI_PROVIDER` from `.env` at call time (deliberately not UI-switchable). Gemini calls auto-retry 3x with backoff on 503/429 (Google-side overload/rate-limit, common across all Gemini models). To add a new AI provider (e.g. Claude, OpenAI): subclass `AIProvider`, implement `generate()` and `health_check()`, register it in the `get_ai_provider()` factory.

### Runtime Settings (`services/runtime_settings_service.py`)
A small, deliberate exception to ".env-only" config: the **Gemini model** (not the provider) is switchable live from the UI, stored as a Mongo override that `get_ai_provider()` checks ahead of the `.env` default. This exists because each Gemini model has its own separate free-tier quota - being stuck on one overloaded/rate-limited model until a redeploy isn't useful. Follow this same pattern (Mongo override, `.env` fallback) for any other setting that genuinely benefits from being changed without a restart.

### Email Provider (`services/email_service.py`)
Same dispatch pattern as AI - `send_email()` routes to `_send_via_custom_relay/_send_via_mailjet/_send_via_brevo/_send_via_sendgrid/_send_via_smtp` based on `EMAIL_PROVIDER`. All five implement the same signature: `(subject, html_body, recipient, attachments) -> dict` where `attachments` is `list[tuple[bytes, str]]` (content, filename) - not file paths, since files are stored in Mongo (see Gotchas). `custom` posts to your own self-hosted relay API instead of a third-party ESP - useful since brand-new ESP accounts commonly get flagged/gated (Mailjet auto-blocks, Brevo requires manual approval) as an anti-abuse measure. To add a new provider, write a `_send_via_x()` function and add one `if` branch in `send_email()`.

### Job Sources (`services/job_sources.py`)
Each source is a function `fetch_x(config: dict) -> list[dict]` returning normalized listings (`title, company, description, location, url, source, salary_text, job_type, posted_at`). Registered in `SOURCE_FETCHERS`. Filtering (relevance, location, language, etc.) is **not** done per-source - it's centralized in `job_search_service.py` so every source gets consistent treatment. To add a source: write the fetcher, register it in `SOURCE_FETCHERS`.

### Config-Driven Behavior
The Job Search Config (name, skills, locations, salary range, keywords, job sources, language, `job_posted_within_days`, etc.) is stored as one document in Mongo and edited as raw JSON from the UI - not scattered across a dozen form fields. `default_resume` and `default_cover_letter` in that JSON are **derived, not hand-typed** - they auto-sync whenever you mark a resume/cover letter as default (see `resume_service.set_default_resume()`).

### Frontend Design System (`frontend/css/style.css`)
A dark-sidebar dashboard layout (not Bootstrap's default top-nav-tabs) with CSS custom properties for the token system (colors, spacing, radii - see the `:root` block). Bootstrap's own CSS variables (`--bs-primary`, `--bs-success`, etc.) are overridden there too, so existing `badge bg-success`/`btn btn-primary`/etc. classes throughout `app.js` automatically pick up the palette without needing every call site touched. Job status renders as color-coded `.status-pill.status-{value}` pills (a real pipeline sequence, so the per-stage color treatment is deliberate, not decorative). Tab-switching JS (`[data-tab]` + `.tab-pane`/`.d-none`) is markup-agnostic, so the sidebar layout itself can be restructured freely without touching JS.

## Local Development Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill in at least MONGO_URI and an AI provider
```

You need MongoDB running somewhere reachable (local install, Docker, or Atlas):
```bash
docker run -d -p 27017:27017 mongo:7
```

Run it:
```bash
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000 (serves frontend + API together) and http://localhost:8000/docs (Swagger).

Or via Docker Compose (brings up Mongo/Redis/Qdrant/Ollama/backend together):
```bash
cd docker && docker compose up -d
```

## Testing Changes Before Deploying

**Always test with a real HTTP request, not just route registration.** A route can appear in `app.routes` and still be unreachable (this bit us once - see Gotchas). Use `TestClient`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
r = client.get("/api/version")
print(r.status_code, r.json())
```

For anything touching Mongo, you need a real (or test) database connection - `TestClient` doesn't mock that away.

## Gotchas / Lessons Learned

- **StaticFiles mount ordering.** `app.mount("/", StaticFiles(...))` matches *every* path as a catch-all. Any `@app.get()` defined textually after it in `main.py` is silently unreachable (returns 404) even though it shows up in `app.routes`. All ad-hoc routes (`/api/health`, `/api/version`) must be defined **before** the mount. Routers added via `include_router()` are unaffected since those are registered earlier in the file already.
- **Python version pinning.** Render (and some other platforms) may default to a very new Python version where dependencies like `pydantic-core` don't have prebuilt wheels yet, causing a Rust compile step that fails in read-only build sandboxes. `backend/.python-version` pins this - keep it in sync with `render.yaml`'s `PYTHON_VERSION` env var.
- **Free-tier filesystems are ephemeral - store user files in the database, not on disk.** Resumes/cover letters were originally stored on local disk; Render's free tier wipes the filesystem on every deploy, so the file record survived in Mongo but the actual bytes silently vanished. Worse, the attach-to-email code checked `if path.exists()` and quietly skipped the attachment instead of erroring - so emails "sent successfully" with nothing attached, no error anywhere. Fixed by storing file bytes directly in Mongo (base64) instead of disk. Lesson: on any platform with an ephemeral filesystem, don't silently skip a missing file you expected to exist - either don't rely on disk persistence at all, or fail loudly if a referenced file is missing.
- **Free-tier SMTP is blocked almost everywhere.** Render, Vercel, Azure, and most free/entry cloud tiers block outbound SMTP ports (25/465/587) as an anti-spam policy - this is industry-standard now, not platform-specific. HTTP-based email APIs (Mailjet/Brevo/SendGrid, or your own self-hosted relay) are the portable fix, since HTTPS (443) is never blocked.
- **New email-provider accounts get flagged.** Brand-new accounts on any ESP immediately trying to send via API is a common spam signature - expect either a manual approval step (Brevo) or an automated temporary block (Mailjet) on a fresh signup. Not a bug, just how these services protect their sender reputation.
- **Word-boundary matching for keywords.** A naive substring check on a short keyword like `"Git"` will match inside unrelated words (`"digital"` contains `"git"`). `job_matching.keyword_hits()` uses regex word boundaries for pure-alphanumeric terms and falls back to plain substring matching for terms with punctuation (`.NET`, `C#`) since `\b` doesn't behave intuitively next to non-word characters.
- **Git line endings on Windows.** If you see `LF will be replaced by CRLF` warnings, that's normal and harmless (git auto-converting line endings) - not an error.
- **Never extract a zip over an existing repo folder.** This resets `.git` and loses the remote. Copy only the specific changed files.

## Extending the Job Search Pipeline

To add a new relevance filter (e.g. salary range), the pattern to follow:
1. Add a `matches_x()` function to `job_matching.py`, pure function, testable in isolation
2. Read the relevant config field in `job_search_service.search_and_store_jobs()`
3. Add the filter check in the per-job loop, with its own `skipped_x` counter
4. Include the counter in the returned summary dict so the UI can report it

This keeps filtering logic centralized, testable without a live network call, and consistently applied across every job source.
