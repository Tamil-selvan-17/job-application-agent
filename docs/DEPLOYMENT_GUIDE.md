# Deployment Guide

Step-by-step path from a fresh clone to a working, deployed instance on Render, including
every piece of setup friction that's been hit and resolved along the way.

## Overview

```
GitHub repo  --push-->  Render (Blueprint)  --uses-->  MongoDB Atlas (free)
                                             --uses-->  Gemini API (free) or local Ollama
                                             --uses-->  Mailjet/Brevo/SendGrid (email, free)
                                             --uses-->  Adzuna API (optional, job search)
```

Nothing here costs money at the tier described, unless you choose the "paid Render + SMTP" path noted at the end.

---

## 1. MongoDB Atlas (database)

1. Sign up free at [mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register)
2. Create a **Project** -> **Build a Database** -> **M0 Free** tier -> any region
3. Create a database user (username + password) - **save these**
4. **Network Access** -> **Add IP Address** -> **Allow Access from Anywhere** (`0.0.0.0/0`) - required since Render doesn't have a fixed outbound IP on the free tier. Make sure it's **not** set to temporary/expiring.
5. **Database** -> **Connect** -> **Drivers** -> copy the connection string:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<username>`/`<password>` with your actual values. This is your `MONGO_URI`.

## 2. Get a Gemini API key (AI provider)

1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) -> sign in -> Create API key
2. Use model `gemini-2.5-flash` or newer - **do not use `gemini-1.5-flash`**, it's been fully retired by Google and returns 404 regardless of key validity.

*(Alternative: run Ollama locally and set `AI_PROVIDER=ollama` - only works if Ollama is reachable from wherever the app runs, so this is really a local-dev-only option unless you self-host Ollama publicly.)*

## 3. Push to GitHub

```bash
cd job-agent
git init                      # skip if already a repo
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

If push is rejected (non-fast-forward), the remote already has commits:
```bash
git pull origin main --allow-unrelated-histories
# resolve any conflicts (see Troubleshooting below), then:
git push -u origin main
```

## 4. Deploy on Render

1. [render.com](https://render.com) -> sign up (GitHub login is easiest)
2. **New +** -> **Blueprint** -> connect your GitHub repo
3. Render detects `render.yaml` and shows the `job-agent-backend` service
4. **Before/during first deploy**, fill in the env vars marked `sync: false`:
   - `MONGO_URI` - from step 1
   - `GEMINI_API_KEY` - from step 2
5. Apply / Create - watch the build log

If you created the service manually as a plain **Web Service** instead of via **Blueprint**, `render.yaml` won't be read automatically - go to **Settings** and set these by hand:
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 5. Set up email (pick one)

Render's **free tier blocks all outbound SMTP** (ports 25/465/587) - this is a platform-wide policy affecting most free cloud hosts, not specific to this app. The fix is an HTTP-based email API instead of raw SMTP. Four options, in order of recommendation:

### Option A: Your own relay (most reliable - no third-party ESP account at all)
If you (or your company) have a server with normal, unrestricted outbound internet, host a tiny authenticated API there that does the actual SMTP send - the main app just makes a normal HTTPS call to it, same underlying pattern as Mailjet/Brevo, except you control it entirely and skip every ESP account-approval/blocking issue.

Expected JSON contract (adjust `email_service._send_via_custom_relay()` if yours differs):
```json
{
  "fromName": "Your Name",
  "smtpUser": "you@gmail.com",
  "smtpPassword": "your-app-password",
  "smtpHost": "smtp.gmail.com",
  "smtpPort": 587,
  "to": "recipient@example.com",
  "subject": "...",
  "htmlBody": "...",
  "attachments": [{"fileName": "Resume.pdf", "contentBase64": "..."}]
}
```
Render env vars:
```
EMAIL_PROVIDER=custom
CUSTOM_EMAIL_API_URL=https://your-relay-host/api/sendmail
CUSTOM_EMAIL_API_KEY=<optional, if your relay checks an Authorization header>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<your gmail>
SMTP_PASSWORD=<gmail app password>
SMTP_FROM=<your gmail>
```

### Option B: Mailjet (best third-party option - works immediately)
1. Sign up free at [mailjet.com](https://www.mailjet.com) - 200 emails/day, 6000/month, no credit card
2. **Account Settings -> Sender addresses & domains** -> add your email -> click the confirmation link sent to it
3. **Account Settings -> REST API -> API Key Management** -> copy the **API Key** and **Secret Key**
4. Render env vars:
   ```
   EMAIL_PROVIDER=mailjet
   MAILJET_API_KEY=<key>
   MAILJET_API_SECRET=<secret>
   MAILJET_FROM_EMAIL=<your verified sender email>
   MAILJET_FROM_NAME=<your name>
   ```
   Note: brand-new Mailjet accounts can occasionally get auto-flagged/temporarily blocked as an anti-abuse measure (a common signature every ESP watches for: new account immediately sending via API) - if so, use their support chat to request a review, or fall back to another option below.

### Option C: Brevo (also free forever, but needs manual approval)
1. Sign up free at [brevo.com](https://www.brevo.com) - 300/day, no expiry
2. **Settings -> Senders, Domains & Dedicated IPs** -> add sender -> enter the 6-digit code emailed to you (click "Add this sender anyway" if you don't own a custom domain)
3. **Settings -> SMTP & API -> API Keys** -> generate a key (leave "Create MCP server API key" off - not needed)
4. **First send will likely fail with `permission_denied` / "not yet activated"** - this is normal for every new Brevo account. Fix: Brevo dashboard -> help icon -> Support and Tickets -> describe it as a low-volume personal/transactional use case. Usually approved in 1-2 business days.
5. Render env vars:
   ```
   EMAIL_PROVIDER=brevo
   BREVO_API_KEY=<key>
   BREVO_FROM_EMAIL=<your verified sender>
   BREVO_FROM_NAME=<your name>
   ```

### Option D: SendGrid (free tier is now a 60-day trial only)
Same idea (Single Sender Verification, no domain needed), but SendGrid removed their permanent free plan in 2025 - only useful short-term. See `.env.example` for the exact vars.

### If a provider blocks/flags your account
This happens because brand-new accounts immediately sending via API is a common spam signature every ESP watches for - it's about the account, not your code. If one provider is stuck, try another from the list above rather than debugging further; all four are pre-wired in `email_service.py`, just switch `EMAIL_PROVIDER`.

### The paid alternative (skips ESP setup entirely)
If you'd rather not deal with any ESP account and don't have your own relay host: upgrade Render to its smallest paid instance type (~$7/month), which removes the SMTP port block, then use `EMAIL_PROVIDER=smtp` with a [Gmail App Password](https://myaccount.google.com/apppasswords) (requires 2-Step Verification enabled first).

## 6. (Optional) Adzuna - real job listings for your country

Remotive and Arbeitnow are Western remote-job boards with very little coverage outside the US/EU. For actual local coverage (e.g. India), add Adzuna:

1. Sign up free at [developer.adzuna.com](https://developer.adzuna.com)
2. Render env vars:
   ```
   ADZUNA_APP_ID=<id>
   ADZUNA_APP_KEY=<key>
   ADZUNA_COUNTRY=in
   ```
   (`ADZUNA_COUNTRY` is any ISO country code Adzuna supports - `in`, `gb`, `us`, etc.)

Also useful without any extra signup: **Excel bulk import** (Jobs tab -> download the sample
template, fill in rows, upload) lets you add jobs manually sourced from anywhere - LinkedIn,
Naukri, a recruiter's email, etc. - without needing a scraper. And `job_posted_within_days` in
your Job Search Config (default 45, editable in Settings -> Job Search Preferences) controls how
old a listing can be before it's filtered out.

## 7. Verify the deployment

1. Open your Render URL - should load the UI
2. `/docs` - should load Swagger
3. `/api/version` - note the version string
4. In the UI, **Settings** tab -> **Test Connection** (AI) and **Send Test Email** - both should succeed
5. **Job Search Config** tab -> paste in your skills/locations/etc. -> Save
6. **Jobs** tab -> **Search Jobs Now**

---

## Redeploying After Changes

```bash
git add .
git commit -m "describe the change"
git push
```
Render auto-redeploys on every push to `main`. Check the **Events** tab if it doesn't trigger automatically, or use **Manual Deploy -> Deploy latest commit**.

**Always confirm the deploy actually landed** by checking `/api/version` (or the navbar badge) against what you expect - route registration existing in code doesn't guarantee the live server is running that code yet.

---

## Troubleshooting

### `ERROR: Could not open requirements file`
Render is building from the repo root instead of `backend/`. Set **Root Directory** to `backend` in service Settings (only auto-applies via Blueprint deploys, not manual Web Service creation).

### Build fails on `pydantic-core` with a Rust/maturin/cargo error
Render picked a Python version too new for the pinned dependency versions to have prebuilt wheels. Confirm `backend/.python-version` contains `3.12.6` and that **Root Directory** is set correctly (the file needs to be found in the service's actual root).

### `git push` rejected: non-fast-forward
```bash
git pull origin main --allow-unrelated-histories
```
If a merge conflict appears (commonly in `.python-version`), open the file, remove the `<<<<<<<`/`=======`/`>>>>>>>` markers, keep the correct content, then:
```bash
git add <file>
git commit -m "Resolve merge conflict"
git push
```

### `fatal: 'origin' does not appear to be a git repository`
The remote isn't configured (often from extracting a zip over an existing repo, which resets `.git`):
```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Stuck in Vim after a git command
`Esc` then type `:wq` then Enter. Avoid it entirely next time with `git pull --no-edit`.

### Email: `[Errno 101] Network is unreachable`
Only relevant if using `EMAIL_PROVIDER=smtp`. This happens when DNS resolves the SMTP host to an IPv6 address the platform can't route. Already handled in code (`_force_ipv4_dns()` in `email_service.py`) - but on Render's **free** tier, SMTP is blocked outright regardless (see next).

### Email: `{"detail":"timed out"}`
Confirms Render's free-tier SMTP port block (not a code issue) - switch to an HTTP-based provider (Section 5).

### AI: 404 on `generateContent`
You're using a retired Gemini model name. Set `GEMINI_MODEL=gemini-2.5-flash` (or check [ai.google.dev](https://ai.google.dev) for the current recommended model - Google periodically retires older versions).

### Jobs list shows irrelevant results
Check `/api/version` first - filtering fixes only apply going forward, they don't retroactively clean up jobs already stored. Use **Clear "New" Jobs** on the Jobs tab, then **Search Jobs Now** again.

### "Apply Now" still lands on the aggregator's page
Only true for jobs added *after* the resolve-url fix (Stage 7+) - check `/api/version`. Some redirect pages use JavaScript instead of HTTP redirects, which has a regex fallback but isn't foolproof for every possible redirect implementation.

### Resume/cover letter emails send successfully but arrive with no attachment
Fixed in Stage 8.1 - files used to be stored on local disk, which Render's free tier wipes on every deploy. They're now stored in MongoDB instead. If you're still seeing this, check `/api/version` is `stage8.1` or later, and **re-upload** your resume/cover letter once after updating (anything uploaded before that fix has no recoverable file bytes - only the database record survived).

### Navbar/sidebar version badge shows "unknown" even though you just deployed
This was a real routing bug (Stage 7.4): `/api/health` and `/api/version` were defined *after* the frontend's catch-all static file mount in `main.py`, which silently shadowed them. Fixed by moving them before the mount. If you see this on a very old deploy, update to the latest code.

### AI: `503 Service Unavailable` on Gemini
A real, widely-reported Google-side capacity issue across all Gemini models (especially spikes after new model releases), not specific to your key. The app retries automatically 3x with backoff. If it's still failing, switch models in Settings -> the Gemini Model dropdown (each model has its own separate free-tier quota, so a different model may not be rate-limited/overloaded even when another is).

### An email provider (Mailjet/Brevo/SendGrid) blocks or flags your account
Common anti-abuse behavior for brand-new accounts immediately sending via API - not a bug in your setup. See Section 5's "If a provider blocks/flags your account" for the fix (usually: contact their support, or switch to a different provider from the list while waiting).
