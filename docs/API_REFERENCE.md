# API Reference

Base URL: your deployed URL (e.g. `https://job-agent-backend.onrender.com`) or `http://localhost:8000` locally.
Interactive Swagger docs are always available at `/docs`.

No authentication - every endpoint is open (single-user personal tool).

---

## System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check (used by Render's health check) |
| GET | `/api/version` | Returns `{"version": "..."}` - bumped every deploy, check this to confirm what's actually live |

## Settings

| Method | Path | Description |
|---|---|---|
| GET | `/api/settings` | Shows active AI provider + effective Gemini model + whether email is configured. AI provider stays `.env`-only; `gemini_model` is switchable live (see below) |
| PUT | `/api/settings/gemini-model` | Switches the Gemini model immediately, no redeploy. Body: `{"model": "gemini-2.5-flash"}`. Persists in Mongo (survives restarts); falls back to `GEMINI_MODEL` from `.env` if never set |
| GET | `/api/settings/ai/health` | Tests connectivity to the currently active AI provider + model |

## AI

| Method | Path | Description |
|---|---|---|
| POST | `/api/ai/generate` | Generic passthrough to the active AI provider. Body: `{"prompt": "...", "system": "..."}` |

## Job Search Config

The JSON blob (skills, locations, salary range, keywords, job sources, language, `website_link`, `job_posted_within_days`, etc.) that drives search and matching.

| Method | Path | Description |
|---|---|---|
| GET | `/api/config` | Current config |
| PUT | `/api/config` | Full replace |
| PATCH | `/api/config` | Partial update - send only the fields you're changing |
| POST | `/api/config/upload` | Upload a `.json` file to replace it entirely (multipart form, field `file`) |

## Resumes

| Method | Path | Description |
|---|---|---|
| POST | `/api/resumes/upload` | Upload `.pdf`/`.docx` (multipart, field `file`). Query: `?is_default=true` |
| GET | `/api/resumes` | List all resumes (summary) |
| GET | `/api/resumes/default` | The current default resume (404 if none set) |
| GET | `/api/resumes/{id}` | Full detail incl. extracted text |
| PUT | `/api/resumes/{id}/default` | Mark as default - also syncs `default_resume` in the Job Search Config |
| DELETE | `/api/resumes/{id}` | Delete resume + all versions |
| POST | `/api/resumes/{id}/versions` | Upload a new version (multipart, field `file`) |
| GET | `/api/resumes/{id}/versions` | Version history |
| POST | `/api/resumes/{id}/analyze` | AI review: detected skills, ATS suggestions, gaps |

## Cover Letters

Same shape as resumes, no versioning.

| Method | Path | Description |
|---|---|---|
| POST | `/api/cover-letters/upload` | Upload `.pdf`/`.docx`. Query: `?is_default=true` |
| GET | `/api/cover-letters` | List all |
| GET | `/api/cover-letters/default` | Current default (404 if none) |
| GET | `/api/cover-letters/{id}` | Detail |
| PUT | `/api/cover-letters/{id}/default` | Mark as default - syncs `default_cover_letter` in config |
| DELETE | `/api/cover-letters/{id}` | Delete |

## Jobs

| Method | Path | Description |
|---|---|---|
| POST | `/api/jobs` | Add a job manually. Body: `{title, company, description, location, url, source, salary_text, hr_email}` |
| GET | `/api/jobs/import-excel/template` | Downloads a sample `.xlsx` with the exact expected columns |
| POST | `/api/jobs/import-excel` | Bulk-adds jobs from an uploaded `.xlsx` (multipart, field `file`). Columns: Company Name, Location, Job Description, HR Email, Role Name, Job URL, Salary (optional). File is parsed in memory only, never stored |
| GET | `/api/jobs` | List jobs. Query: `?status=new\|saved\|applied\|rejected\|interview\|offer\|not_responded`, `?min_match=70` (only jobs with an AI match score >= this; unanalyzed jobs excluded when set) |
| DELETE | `/api/jobs/clear` | Bulk delete. Query: `?status=new` (default - only clears untouched listings) or `?status=all` |
| POST | `/api/jobs/analyze-unanalyzed` | Batch-runs AI analysis on jobs with no match score yet. Query: `?resume_id=...`, `?limit=15` (cap, default 15) |
| GET | `/api/jobs/{id}` | Full detail incl. analysis, application tracking |
| PUT | `/api/jobs/{id}` | Update fields/status/notes. Setting `status=applied` auto-records `applied_at` |
| DELETE | `/api/jobs/{id}` | Delete one job |
| POST | `/api/jobs/{id}/analyze` | AI extraction + ATS match score against a resume. Query: `?resume_id=...` (defaults to your default resume) |
| GET | `/api/jobs/{id}/resolve-url` | Follows redirects (incl. JS/meta-refresh fallback) to find the real employer URL, past aggregator tracking links (e.g. Adzuna) |
| POST | `/api/jobs/{id}/apply-email/preview` | Returns `{subject, html_body, hr_email_guess}` without sending - for review before sending |
| POST | `/api/jobs/{id}/apply-email` | Sends the application email (resume + cover letter attached). Body: `{hr_email, resume_id?, cover_letter_id?, subject?, html_body?}` - subject/html_body optional overrides from the preview step |

### Job status lifecycle
`new` -> `saved` -> `applied` -> `rejected` / `interview` / `offer` / `not_responded`

`not_responded` is set automatically by the daily follow-up processor if an applied job gets no
reply within 10 days (see Notifications section below) - not usually set manually.

### Application tracking fields (on job detail)
`applied_at`, `application_method` (`"website"` or `"email"`), `application_email_to`, `hr_email`
(authoritative, from Excel import or manual entry), `hr_email_guess` (auto-detected fallback),
`reminder_1_sent_at`, `reminder_2_sent_at`, `reminder_3_sent_at`

## Job Search (automated)

| Method | Path | Description |
|---|---|---|
| POST | `/api/jobsearch/run` | Triggers a search across configured sources now. Returns counts: `fetched_total`, `new_jobs_added`, and skip breakdowns (`skipped_duplicate`, `skipped_irrelevant`, `skipped_language`, `skipped_location`, `skipped_job_type`, `skipped_experience`, `skipped_stale`, `skipped_filtered`) |
| GET | `/api/jobsearch/sources` | Lists implemented sources (Remotive, Arbeitnow, Adzuna) vs. not-yet-implemented ones (LinkedIn, Indeed, Naukri, Wellfound, etc.) |

## Notifications

| Method | Path | Description |
|---|---|---|
| GET | `/api/notifications/status` | `{"configured": bool, "provider": "mailjet\|brevo\|sendgrid\|custom\|smtp"}` |
| POST | `/api/notifications/test-email` | Sends a test email to confirm the active provider works |
| GET | `/api/notifications/followups/due` | Applied jobs with a reminder stage (1st/day 3, 2nd/day 5, 3rd/day 8) due and unsent. Each entry includes `next_reminder_stage` (1/2/3) |
| POST | `/api/notifications/followups/{job_id}/preview` | Returns `{subject, html_body, hr_target}` without sending, for review/editing first. Query: `?stage=1\|2\|3` (defaults to whichever stage is next due) |
| POST | `/api/notifications/followups/{job_id}/send` | Sends the next-due reminder stage for one job now (to its `hr_email`/`hr_email_guess` if set, otherwise notifies you instead), and marks that stage sent. Body (optional): `{subject, html_body}` overrides from `/preview`, possibly edited |
| POST | `/api/notifications/followups/run-all` | Manually triggers the full daily follow-up cycle now (normally runs automatically once a day) - sends all newly-due reminders and auto-marks day-10+ jobs `not_responded` |

---

## Common Response Shapes

**Job summary** (list view):
```json
{"id": "...", "title": "...", "company": "...", "location": "...", "source": "Adzuna",
 "status": "new", "created_at": "...", "updated_at": "...", "match_percent": 82}
```

**Job analysis** (nested in job detail after `/analyze`):
```json
{
  "provider": "gemini", "analyzed_at": "...", "resume_id": "...",
  "extracted_skills": [], "responsibilities": [],
  "experience_required": "3-5 years", "salary_range": "...", "benefits": [],
  "required_keywords": [], "match_percent": 82,
  "match_reason": "...", "missing_skills": [],
  "learning_suggestions": [], "interview_difficulty": "Medium"
}
```

**Error responses** follow FastAPI's default shape: `{"detail": "message"}` with an appropriate 4xx status.
