# AI Job Application Agent

A personal AI-powered job application assistant: finds jobs matching your skills, scores them
against your resume with AI, and helps you apply — either one-click through the employer's site
or via a professional application email with your resume attached — while tracking every
application and automating follow-ups.

No authentication (single-user, personal tool by design). AI provider/model (Ollama or Gemini,
with live model switching) and email provider (your own relay, Mailjet, Brevo, SendGrid, or SMTP)
are both configured via `.env` and swappable without touching code.

## Documentation

| Doc | What's in it |
|---|---|
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Step-by-step: MongoDB Atlas, Gemini, Render, email provider setup, troubleshooting |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Architecture, project structure, local dev setup, how to extend it |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Every endpoint, request/response shapes |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Detailed history of what was built at each stage and why |

## Quick Start

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # fill in MONGO_URI + an AI provider at minimum
uvicorn app.main:app --reload --port 8000
```
Open `http://localhost:8000` (UI) and `http://localhost:8000/docs` (Swagger).

For the full path to a live deployment on Render, see the [Deployment Guide](docs/DEPLOYMENT_GUIDE.md).

## What It Does

- **Resumes & cover letters** — upload `.pdf`/`.docx` (stored in MongoDB, not local disk, so
  they survive redeploys), auto-extract text, version history, set a default (auto-synced into
  your search config), AI-powered resume review
- **Job search** — pulls live listings from Remotive, Arbeitnow, and Adzuna (free public/keyed
  APIs — LinkedIn/Indeed/Naukri need browser automation, deliberately not built due to ToS/ban
  risk), filtered by your skills, location, language, job type, experience level, and posting
  freshness (configurable via `job_posted_within_days`)
- **Excel bulk import** — add many jobs at once from a `.xlsx` (Company, Location, Description,
  HR Email, Role, URL, Salary) using a downloadable template; the file is parsed in memory and
  never stored, only the row data
- **ATS matching** — AI extracts skills/requirements from each job description and scores it
  against your resume: match %, missing skills, learning suggestions, interview difficulty. Live
  Gemini model switching in Settings if one model is overloaded/rate-limited (each has its own quota)
- **Apply two ways, both tracked** — "Apply Now" opens the real employer page (resolves past
  aggregator tracking links) and marks it applied; or send a professional HR application email
  (resume + cover letter attached, portfolio link, your real skills) with a preview-before-send step
- **Multi-stage automated follow-ups** — for applied jobs: 1st reminder at day 3, 2nd at day 5,
  3rd at day 8 (sent to the job's HR email, each with a preview-before-send step), auto-marked
  "Not Responded" at day 10 with no reply
- **Email notifications** — new matching jobs found, and follow-up reminders
- **Daily automation** — a background scheduler runs the search and follow-up cycle once a day
  (works while the server is awake; Render's free tier sleeps after ~15 min idle)

## Tech Stack

FastAPI + MongoDB backend, plain HTML/Bootstrap/JS frontend (no build step, custom dashboard
design system), Ollama/Gemini for AI, your-own-relay/Mailjet/Brevo/SendGrid/SMTP for email,
APScheduler for automation, openpyxl for Excel import. See the
[Developer Guide](docs/DEVELOPER_GUIDE.md) for the full breakdown and how everything fits together.

## Known Limitations (by design, not oversight)

- **No LinkedIn/Indeed/Naukri scraping** — these require browser automation with login/session/
  CAPTCHA handling, carrying real ToS-violation and account-ban risk. Adzuna and Excel import are
  the practical alternatives instead.
- **No unattended auto-apply** — every company uses a different application system with no
  reliable generic way to fill them correctly, and silently submitting your data without you
  reviewing it first is a real risk. The email-apply flow is the closest safe equivalent: one
  click gets you a ready email, you still see it before it sends.
- **HR email isn't guessed from a company name pattern** (e.g. `hr@company.com`) — an unverified
  guess risks bouncing or reaching the wrong person. It's pre-filled from Excel import / manual
  entry, or auto-detected when a job description happens to contain an email address.
- **Free-tier SMTP is blocked on most hosts** (Render, Vercel, Azure, etc.) — this app defaults to
  HTTP-based email (your own relay, or Mailjet/Brevo/SendGrid) specifically to route around that,
  since it's a platform-wide policy, not something fixable in this app's code.

## Not Yet Built

Playwright-based scraping for LinkedIn/Indeed/Naukri, embeddings + vector search (Qdrant),
analytics dashboard, admin panel, auth.
