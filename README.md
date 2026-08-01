# AI Job Application Agent — Core (Stage 1–4)

No authentication (single-user local setup, as requested). AI provider
(**Ollama or Gemini**) is configured purely via `.env` — no UI toggle;
edit `.env` and restart to switch. Job-search JSON config is editable
anytime from the UI.

## What's included so far

**Stage 1 — Core**
- FastAPI backend, MongoDB connection, `AI Provider` abstraction
  (Ollama/Gemini switch via `.env`), job-search JSON config editable
  from the UI, Docker Compose for Mongo/Redis/Qdrant/Ollama

**Stage 2 — Resume Management**
- Upload `.pdf`/`.docx`, auto text extraction, version history, default
  resume, AI-powered resume analysis (skills, ATS suggestions, gaps)

**Stage 3 — Jobs & ATS Match Scoring**
- Manual job entry, `POST /api/jobs/{id}/analyze` for AI extraction +
  ATS match % against a resume, status tracking

**Stage 4 — Automated Job Search & Email Notifications**
- `POST /api/jobsearch/run` — pulls listings from **Remotive** and
  **Arbeitnow** (free, public, keyless job-board APIs), filtered by your
  Job Search Config (skills, keywords include/exclude, company
  blacklist/whitelist, remote preference), deduped by URL against jobs
  already stored, capped at `daily_job_limit`
  - `GET /api/jobsearch/sources` — lists what's implemented vs. not
  - **Not implemented**: LinkedIn/Indeed/Naukri/Wellfound/etc. — these
    require browser automation (login, sessions, CAPTCHA handling via
    Playwright), which is materially riskier (ToS violations, account
    bans) and is a separate future stage, not bundled into this one
- Email notifications via SMTP (`app/services/email_service.py`):
  - New-jobs digest after a search finds matches
  - Follow-up reminder for applications past `followup_after_days`
    with no reminder sent yet
  - `POST /api/notifications/test-email` to verify SMTP setup
  - `GET /api/notifications/followups/due` + per-job "send now" button
- A background scheduler (APScheduler) runs the job search and
  follow-up check once a day automatically (configurable hour via env)
  — **caveat:** on Render's free tier the process sleeps after ~15 min
  idle, so this fires reliably only if something keeps the service
  awake (paid "always on" plan, or an external uptime pinger). The
  manual "Search Jobs Now" button and test-email endpoint always work
  regardless.

Endpoints added in this stage:
```
POST   /api/jobsearch/run                    trigger a job search now
GET    /api/jobsearch/sources                list implemented/unimplemented sources
GET    /api/notifications/status             is SMTP configured?
POST   /api/notifications/test-email         send a test email
GET    /api/notifications/followups/due      applications needing a follow-up
POST   /api/notifications/followups/{id}/send   send + mark that job's reminder sent
```

## Setting up email notifications

Add to `backend/.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password    # Gmail: myaccount.google.com/apppasswords, NOT your login password
SMTP_FROM=you@gmail.com
NOTIFY_EMAIL_TO=                           # optional - defaults to the "email" field in your Job Search Config
```
Any SMTP provider works the same way (Outlook, SendGrid/Mailgun SMTP relay, etc.) — just change host/port/credentials.

**Stage 5 — Search Relevance Fix, Apply Now, Cover Letters**
- **Fixed a real bug**: job-search relevance filtering used plain
  substring matching, so a keyword like `"Git"` matched inside
  unrelated words like **"digital"** (di-**git**-al), letting irrelevant
  jobs through even with a correct config. Replaced with word-boundary
  regex matching (`app/services/job_matching.py`) that only matches
  whole words/phrases, and now requires **at least 2 distinct
  skill/keyword hits** (not just 1) before keeping a job - both
  Remotive and Arbeitnow results are filtered through this same central
  logic instead of each source doing its own (inconsistent) filtering.
- Remotive search now runs a couple of *separate* targeted queries
  (your top `keywords_include`, or skills if none set) and merges
  results, instead of joining several keywords into one ambiguous
  search string
- **Apply Now** button on each job: opens the job's URL in a new tab
  and marks it `applied` (records `applied_at` for follow-up
  reminders). This is a human-in-the-loop "one-click apply" - it does
  **not** auto-fill forms or submit anything without you; true
  unattended auto-apply needs browser automation (Playwright), which
  remains a deliberately separate, higher-risk future stage
- **Cover letter management** (`/api/cover-letters/*`): upload
  `.pdf`/`.docx`, set a default, delete - mirrors resumes but without
  version history
- **`default_resume`/`default_cover_letter` in your Job Search Config
  now sync automatically** from whichever resume/cover letter you mark
  default in the Resumes tab - you don't type a filename by hand
  anymore, and it updates immediately when you change your default

**Stage 5.1 — Language Filter, Clear Jobs, Deploy Verification**
- **Language filtering**: jobs whose description isn't detected as your
  configured language (default English) are skipped during search
  (`langdetect`). Change it via the new **Job Search Preferences**
  dropdown in Settings, or `language` in your Job Search Config JSON -
  they're the same field.
- **Clear "New" Jobs** button on the Jobs tab (`DELETE /api/jobs/clear`)
  - only removes untouched `status="new"` listings, never anything
  you've saved/applied to/tracked - useful for wiping out stale results
  that were added before a filtering fix shipped.
- **`GET /api/version`** + a badge in the navbar - bump `APP_VERSION` in
  `main.py` on every change and check this badge after a deploy to
  confirm Render is actually running the code you think it is, instead
  of guessing.
- The "Search Jobs Now" result message now shows exactly how many jobs
  were skipped for being not-relevant-enough vs. wrong-language vs.
  filtered, so it's clear which lever to adjust if results still look off.

**Stage 5.2 — Location Filtering, Adzuna, Job Type/Experience/Freshness**
- **Real bug fixed**: `preferred_locations` in your config was never
  actually used anywhere. Also, `remote: true` was being passed to
  sources as a strict `remote_only` filter, which **excluded every
  on-site job entirely** - backwards from "remote OR my preferred
  cities." Both fixed in `job_matching.matches_location()`.
- **Added Adzuna** (`developer.adzuna.com`, free signup) as a source -
  Remotive/Arbeitnow are Western remote-job boards with almost no India
  coverage, which is the real reason Chennai/Bangalore never showed up
  even with correct filtering. Adzuna actually indexes India and
  supports server-side location + recency search. Set `ADZUNA_APP_ID`
  and `ADZUNA_APP_KEY` in `.env` to enable it (skipped silently if unset).
- Added soft filters for **job type** (Full Time/Contract/etc., only
  applied when a source reports it), **experience** (rejects only
  clearly-over-senior postings via regex-extracted years, with a buffer
  - free-text extraction is noisy so this errs toward keeping ambiguous
  cases rather than wrongly excluding good matches), and **posting
  freshness** (skips listings older than 45 days when a source reports
  a date).
- **LinkedIn/Indeed**: no free, legal public API exists for third-party
  apps to search these directly - actual integration means either
  Playwright-based scraping (ToS/ban risk, a separate deliberately
  out-of-scope stage) or a paid aggregator. Adzuna is the practical
  middle ground: legitimate API, free tier, and it aggregates listings
  from many boards.
- "Search Jobs Now" now reports separate skip counts for location, job
  type, experience, and staleness, alongside relevance/language, so
  it's clear which filter to loosen if results are ever too narrow.

**Stage 6 — Professional HR Application Email**
- **`website_link`** added to your Job Search Config JSON - your
  portfolio/personal site, included in application emails
- **"Apply Now (Website)"** button: opens the job's URL and marks it
  applied with `application_method: "website"`. Worth knowing how
  Adzuna's URLs work: `redirect_url` from their API routes through
  Adzuna's own tracking before landing on the employer's real
  application page - that's standard for job aggregators, not a bug.
- **"Email HR / Recruiter Instead"**: composes and sends a professional
  application email (`POST /api/jobs/{id}/apply-email`) with your
  default resume attached (cover letter too, if you have one set), your
  top skills, portfolio link, and contact info pulled straight from your
  Job Search Config - not a template you have to fill in each time. The
  HR/recruiter email field auto-fills if one is found in the job
  description text (common for smaller-company listings); double-check
  it before sending. On success, marks the job applied with
  `application_method: "email"` and records the recipient for tracking.
- Both apply paths now show an "Applied via X on [date]" line in the
  job detail so it's clear how and when each application went out.

**Stage 7 — Preview-Before-Send Email, Real Apply URLs, Match % Filter**
- **HR email auto-detection persisted server-side**: `hr_email_guess` is
  extracted from the job description and stored on every job (search
  results and manual entries), pre-filled in the Email HR panel.
  Deliberately **not** implemented: guessing addresses like
  `hr@company.com` from the company name - an unverified guess risks
  bouncing or reaching the wrong person, worse than just typing it in
  when it's not in the posting.
- **"Apply Now" resolves the real destination URL**
  (`GET /api/jobs/{id}/resolve-url`) - follows redirects server-side so
  it opens the actual employer page instead of landing on Adzuna's
  intermediate tracking page. This is the same redirect a browser click
  would follow anyway, just done server-side for a cleaner UX.
- **Full unattended auto-apply (bot-filling and submitting forms on
  arbitrary company websites) was deliberately not built.** Every
  company uses a different application system (Greenhouse, Lever,
  Workday, custom forms) with no reliable generic way to fill them
  correctly, and silently submitting your data without you reviewing it
  first is a real risk. The Email HR flow below is the closest safe
  equivalent.
- **Email now previews before sending**
  (`POST /api/jobs/{id}/apply-email/preview` -> edit subject/body in the
  UI -> `POST /api/jobs/{id}/apply-email` with the edited text) instead
  of sending blind on one click.
- **Match-score filtering**: "Min match %" filter on the Jobs tab, plus
  "Analyze All Unanalyzed (AI)" to batch-run ATS analysis (capped at 15
  per click - auto-analyzing every found job on every search would burn
  AI quota fast, so it's opt-in).

**Stage 7.1 — SMTP Fix, Redirect Reliability**
- **Fixed `[Errno 101] Network is unreachable` on email send** - this
  happens on Render (and several other PaaS hosts) because Python's DNS
  resolution picks an IPv6 address for the SMTP server (Gmail has AAAA
  records) but Render's outbound network can't actually route IPv6, so
  the connection fails immediately. Forced IPv4-only DNS resolution for
  the duration of the SMTP connection (`_force_ipv4_dns()` in
  `email_service.py`) - doesn't touch the hostname used for TLS/SNI, so
  certificate validation is unaffected.
- **Hardened `resolve-url`**: some redirect pages use JavaScript or
  `<meta http-equiv="refresh">` instead of a real HTTP 3xx redirect,
  which `httpx`'s automatic redirect-following can't see - added a
  regex fallback that scans the page for a further destination when the
  resolved URL still points at the aggregator's own domain. Also sends
  a normal browser User-Agent, since some redirect services silently
  serve a different (non-redirecting) page to obvious bot/script clients.
- Note: `hr_email_guess` only populates for jobs added *after* Stage 7
  deployed (older stored jobs won't retroactively get it), and stays
  empty for postings that never mention an email at all - both expected,
  not bugs.

**Stage 7.2 — The Real Fix for Email on Render's Free Tier**
- **Root cause found**: Render's free tier blocks **all** outbound SMTP
  ports (25, 465, 587) as a platform policy since September 2025 -
  confirmed via Render's own changelog. This is why email kept failing
  with `[Errno 101] Network is unreachable` then `timed out` no matter
  what SMTP settings were tried - it was never fixable from the app
  side; the previous IPv4-DNS fix helped locally/on paid plans but
  couldn't get past this.
- **Fix**: added SendGrid's HTTP API as an alternate email provider -
  it sends over normal HTTPS (not blocked) instead of raw SMTP. Set
  `EMAIL_PROVIDER=sendgrid` in `.env` (Render), keep `smtp` for local
  dev. SendGrid's free tier supports **Single Sender Verification** -
  verifies just your Gmail address directly (no custom domain/DNS
  access required), which matches a personal-project setup with no
  domain of your own:
  1. Sign up free at sendgrid.com
  2. Settings -> Sender Authentication -> Single Sender Verification ->
     verify your Gmail address (click the link they email you)
  3. Settings -> API Keys -> create one with "Mail Send" permission
  4. Set in `.env`: `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` (must
     match the verified address), `SENDGRID_FROM_NAME`
- Settings tab now shows which provider is active and whether it's configured.

**Stage 7.3 — Brevo Replaces SendGrid as the Recommended Provider**
- SendGrid **removed its permanent free plan in March 2025** - the
  "free" option is now a 60-day trial only (confirmed by your own
  SendGrid dashboard screenshot showing "Trial ends September 30th").
  Not a mistake in setup; it's a genuine change on their end.
- Added **Brevo** (formerly Sendinblue) as the new default
  (`EMAIL_PROVIDER=brevo`) - confirmed via multiple independent sources
  to have a **genuinely permanent** free plan: 300 emails/day, full
  transactional API access, no expiration. Sender verification is a
  6-digit code emailed to you - no custom domain/DNS needed, same as
  SendGrid's Single Sender option.
- Setup:
  1. Sign up free at brevo.com
  2. Settings -> Senders, Domains & Dedicated IPs -> add your Gmail as
     a sender -> enter the 6-digit code they email you
  3. Settings -> SMTP & API -> API Keys -> generate a new key
  4. Set in `.env`: `BREVO_API_KEY`, `BREVO_FROM_EMAIL` (must match the
     verified sender), `BREVO_FROM_NAME`
- SendGrid support is still in the code (`EMAIL_PROVIDER=sendgrid`) in
  case you want to use it during its 60-day trial window, but it's no
  longer the default recommendation.

**Stage 7.4 — Fixed the Version Badge (Real Routing Bug) + Brevo Activation**
- **Real bug found and fixed**: `/api/health` and `/api/version` were
  defined *after* `app.mount("/", StaticFiles(...))` in `main.py`. Since
  a `Mount("/")` matches every path as a catch-all, and Starlette
  matches routes in registration order, both endpoints were silently
  unreachable (404) despite showing up in `app.routes` - which is why
  earlier testing (checking route registration only) didn't catch it.
  Confirmed via `TestClient` making an actual request before and after
  the fix. **Any future ad-hoc `@app.get()` routes must be defined
  before the StaticFiles mount, not after** - routers added via
  `include_router()` are unaffected since those are already registered
  earlier in the file.
- **Brevo requires manual account activation** for transactional email
  sending on every new account - separate from having a valid API key.
  If you see `"Your SMTP account is not yet activated"`: Brevo -> help
  icon (top right) -> Support and Tickets -> describe your use case
  (personal job-application tool, low volume, transactional) -> usually
  approved within 1-2 business days. Not fixable from the app side;
  it's Brevo's anti-abuse review process for every new account.

**Stage 7.5 — Mailjet: Free Email With No Approval Wait**
- Added **Mailjet** (`EMAIL_PROVIDER=mailjet`) as the new recommended
  provider - permanent free plan (200/day, 6000/month, no credit card,
  confirmed across multiple current sources), and unlike Brevo, it does
  **not** gate transactional sending behind a manual support-ticket
  review - it works right after the normal sender-email confirmation
  click.
- Setup:
  1. Sign up free at mailjet.com
  2. Account Settings -> Sender addresses & domains -> Add a sender
     address -> enter your Gmail -> click the confirmation link they email
  3. Account Settings -> REST API -> API Key Management -> copy both the
     **API Key** and **Secret Key** (Mailjet uses a key+secret pair, not
     a single bearer token like Brevo/SendGrid)
  4. Set in `.env`: `MAILJET_API_KEY`, `MAILJET_API_SECRET`,
     `MAILJET_FROM_EMAIL` (must match the validated sender),
     `MAILJET_FROM_NAME`
- Brevo and SendGrid support remain in the code as alternatives if
  preferred - just change `EMAIL_PROVIDER`.

## Not yet built (next stages)

Job scrapers requiring browser automation (LinkedIn/Naukri/etc. via
Playwright), embeddings + Qdrant vector search, dashboard/analytics,
one-click apply, cover letter generation, admin panel, auth. Building
these one at a time on top of this core.

## Deploying to Render

The repo includes `render.yaml` (a Render Blueprint) so Render can
provision the service automatically.

**1. Get a MongoDB connection string.** Render doesn't host MongoDB, so
use a free cluster from [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register):
create a free (M0) cluster, create a database user, and under Network
Access allow `0.0.0.0/0` (or Render's specific egress IPs, for tighter
security). Copy the `mongodb+srv://...` connection string.

**2. Push this repo to GitHub:**
```bash
cd job-agent
git init
git add .
git commit -m "Initial commit: AI job application agent core"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

**3. Deploy on Render:**
- Go to the Render dashboard → **New +** → **Blueprint**
- Connect your GitHub account/repo — Render will detect `render.yaml`
- Before the first deploy completes, set these env vars in the Render
  dashboard (they're marked `sync: false` in `render.yaml` so they're
  never committed to git):
  - `MONGO_URI` — your Atlas connection string
  - `GEMINI_API_KEY` — your Gemini API key (get one at
    [aistudio.google.com](https://aistudio.google.com/apikey))
- Deploy. Render builds from `backend/`, runs
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and serves the
  frontend + API from the same URL.

**Notes / limitations on Render's free tier:**
- **Ollama won't work** on Render unless you self-host it somewhere
  publicly reachable — `render.yaml` defaults `AI_PROVIDER=gemini` for
  this reason. Switch back to `ollama` only if you have a public Ollama
  endpoint.
- **Uploaded resumes are not persisted** across deploys/restarts on
  Render's free plan (ephemeral filesystem) — fine for testing, but for
  production you'd want to point `UPLOAD_DIR` at a persistent disk
  (Render offers paid persistent disks) or swap resume file storage to
  S3/Cloudinary in a later stage.
- Free-tier services spin down after inactivity and take ~30-50s to
  wake on the next request.

## Running locally (without Docker)

1. **Start MongoDB** (needed): install locally or `docker run -d -p 27017:27017 mongo:7`
2. **(Optional) Start Ollama** if you want local AI: `ollama serve` and `ollama pull llama3.1`
3. Backend:
   ```bash
   cd backend
   python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   uvicorn app.main:app --reload --port 8000
   ```
4. Open **http://localhost:8000** — this serves the frontend and API together.
5. Swagger docs: **http://localhost:8000/docs**

## Running with Docker Compose

```bash
cd docker
docker compose up -d
```

This starts Mongo, Redis, Qdrant, Ollama, and the backend together.
Note: the frontend is served by the backend container too, at
`http://localhost:8000`. Redis/Qdrant aren't wired into the app logic
yet — they're provisioned now so later stages (caching, vector search)
can plug straight in.

## Switching AI provider

Edit `backend/.env`:
```
AI_PROVIDER=ollama      # or: gemini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-1.5-flash
```
Restart the server. The Settings tab in the UI shows what's active and
lets you **Test Connection**. Every AI-powered endpoint (resume analysis
now, job matching/cover letters/chat later) automatically uses whichever
provider is set — no other code changes needed.

## Updating your job search config

Go to the **Job Search Config** tab — edit the JSON directly and click
**Save Config**, or use **Upload JSON** to replace it with a file. This
can be done at any time; it takes effect immediately for the next job
search run (once the job-search engine is built in a later stage).
