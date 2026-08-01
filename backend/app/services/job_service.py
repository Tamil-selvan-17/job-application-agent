"""
Job storage (manual entry for now - job source scrapers plug into the
same `jobs` collection in a later stage) plus AI-powered job analysis:
skill/responsibility/keyword extraction from the JD, and an ATS-style
match score against a chosen (or default) resume.
"""
import json
import re
from datetime import datetime, timezone
from bson import ObjectId

from app.database.mongo import get_db
from app.services.ai_provider import get_ai_provider
from app.services import resume_service, cover_letter_service, email_service, config_service
from app.services.job_matching import extract_email

ANALYSIS_SYSTEM_PROMPT = (
    "You are an ATS (Applicant Tracking System) and technical recruiter assistant. "
    "You always respond with STRICT, VALID JSON ONLY - no markdown fences, no commentary, "
    "no text before or after the JSON object."
)

ANALYSIS_PROMPT_TEMPLATE = """Analyze this job description and compare it against the candidate's resume text.
Return a single JSON object with EXACTLY these keys:

{{
  "extracted_skills": [list of strings - technical/professional skills required by the job],
  "responsibilities": [list of strings - key responsibilities],
  "experience_required": "string, e.g. '3-5 years'",
  "salary_range": "string, best guess from JD or 'Not specified'",
  "benefits": [list of strings],
  "required_keywords": [list of strings - important ATS keywords from the JD],
  "match_percent": integer 0-100 - how well the resume matches this job,
  "match_reason": "1-3 sentence explanation of the match score",
  "missing_skills": [list of strings - skills the job wants that are NOT evident in the resume],
  "learning_suggestions": [list of strings - what the candidate should learn/highlight to close the gap],
  "interview_difficulty": "one of: Easy, Medium, Hard, Very Hard"
}}

JOB DESCRIPTION:
---
{job_description}
---

CANDIDATE RESUME TEXT:
---
{resume_text}
---

Return ONLY the JSON object.
"""


def _extract_json(raw: str) -> dict:
    """Best-effort JSON extraction in case the model wraps output in fences or adds stray text."""
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(1)
    return json.loads(text)


async def create_job(data: dict) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        **data,
        "status": "new",
        "notes": "",
        "analysis": None,
        "hr_email_guess": extract_email(data.get("description", "")),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.jobs.insert_one(doc)
    return await get_job(str(result.inserted_id))


async def list_jobs(status: str | None = None, min_match: int | None = None) -> list[dict]:
    db = get_db()
    query = {"status": status} if status else {}
    if min_match is not None:
        # Only jobs that have actually been AI-analyzed carry a match_percent -
        # unanalyzed jobs are excluded rather than guessed at when this filter
        # is active. Use "Analyze All Unanalyzed" first to populate scores.
        query["analysis.match_percent"] = {"$gte": min_match}
    jobs = await db.jobs.find(query).sort("created_at", -1).to_list(length=500)
    return [_to_summary(j) for j in jobs]


async def list_unanalyzed_jobs(limit: int = 15) -> list[dict]:
    db = get_db()
    jobs = await db.jobs.find({"analysis": None}).sort("created_at", -1).to_list(length=limit)
    return [_to_summary(j) for j in jobs]


async def get_job(job_id: str) -> dict:
    db = get_db()
    j = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not j:
        raise ValueError("Job not found")
    return _to_detail(j)


async def update_job(job_id: str, patch: dict) -> dict:
    db = get_db()
    patch = {k: v for k, v in patch.items() if v is not None}
    if patch.get("status") == "applied":
        existing = await db.jobs.find_one({"_id": ObjectId(job_id)})
        if existing and not existing.get("applied_at"):
            patch["applied_at"] = datetime.now(timezone.utc)
    patch["updated_at"] = datetime.now(timezone.utc)
    result = await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": patch})
    if result.matched_count == 0:
        raise ValueError("Job not found")
    return await get_job(job_id)


async def delete_job(job_id: str) -> None:
    db = get_db()
    result = await db.jobs.delete_one({"_id": ObjectId(job_id)})
    if result.deleted_count == 0:
        raise ValueError("Job not found")


async def resolve_apply_url(job_id: str) -> str:
    """
    Some sources (notably Adzuna) give a tracking/redirect URL rather
    than the employer's actual application page - that's standard for
    every job aggregator (they need the click for revenue attribution),
    not a bug. Following the redirect server-side lands the user
    directly on the real destination instead of an intermediate Adzuna
    page, without doing anything the aggregator doesn't already expect
    a normal click to do.

    Handles two redirect styles:
    1. Real HTTP 3xx redirects (httpx follows these natively)
    2. JS/meta-refresh redirects (some tracking pages serve HTML that
       redirects via <meta http-equiv="refresh"> or a JS location change
       instead of an HTTP redirect - httpx can't follow those on its
       own, so this does one extra regex pass over the response body)

    Falls back to the original URL on any error or if no further
    redirect can be found - opening the tracking page is still strictly
    better than a broken link.
    """
    import re
    import httpx

    job = await get_job(job_id)
    url = job.get("url", "")
    if not url:
        raise ValueError("This job has no URL saved")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            final_url = str(resp.url)

            # If we landed on an aggregator's own domain rather than an
            # employer site, the redirect was likely JS/meta-refresh based -
            # scan the HTML for a further destination.
            if "adzuna" in final_url.lower():
                match = re.search(
                    r'(?:url=|window\.location(?:\.href)?\s*=\s*["\'])(https?://[^"\'\s>]+)',
                    resp.text,
                    re.IGNORECASE,
                )
                if match:
                    return match.group(1)

            return final_url
    except Exception:
        return url


async def clear_jobs(status: str | None = "new") -> int:
    """
    Bulk-delete jobs. Defaults to only clearing status="new" (untouched,
    unreviewed listings) so anything you've already saved/applied to/
    tracked an interview for is never wiped out by accident. Pass
    status=None to clear everything regardless of status.
    """
    db = get_db()
    query = {"status": status} if status else {}
    result = await db.jobs.delete_many(query)
    return result.deleted_count


async def preview_application_email(job_id: str) -> dict:
    """Builds the subject+body without sending, so the user can review/edit first."""
    job = await get_job(job_id)
    config = await config_service.get_config()
    preview = email_service.build_application_email_preview(job, config)
    preview["hr_email_guess"] = job.get("hr_email_guess") or ""
    return preview


async def apply_via_email(
    job_id: str,
    hr_email: str,
    resume_id: str | None = None,
    cover_letter_id: str | None = None,
    subject_override: str | None = None,
    html_override: str | None = None,
) -> dict:
    """
    Sends a professional application email to `hr_email` with the
    default (or specified) resume attached, and cover letter if one is
    set. On success, marks the job applied and records how/who it was
    sent to for tracking and follow-up reminders.
    """
    job = await get_job(job_id)

    if resume_id:
        resume_path, resume_filename = await resume_service.get_resume_file(resume_id)
    else:
        default_resume = await resume_service.get_default_resume()
        if not default_resume:
            raise ValueError("No resume specified and no default resume set - upload one first")
        resume_path, resume_filename = await resume_service.get_resume_file(default_resume["id"])

    cover_letter_path, cover_letter_filename = "", ""
    if cover_letter_id:
        cover_letter_path, cover_letter_filename = await cover_letter_service.get_cover_letter_file(cover_letter_id)
    else:
        default_cl = await cover_letter_service.get_default_cover_letter()
        if default_cl:
            cover_letter_path, cover_letter_filename = await cover_letter_service.get_cover_letter_file(default_cl["id"])

    result = await email_service.send_application_email(
        job=job,
        hr_email=hr_email,
        resume_path=resume_path,
        resume_filename=resume_filename,
        cover_letter_path=cover_letter_path,
        cover_letter_filename=cover_letter_filename,
        subject_override=subject_override,
        html_override=html_override,
    )

    if result.get("sent"):
        db = get_db()
        now = datetime.now(timezone.utc)
        await db.jobs.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    "status": "applied",
                    "applied_at": now,
                    "application_method": "email",
                    "application_email_to": hr_email,
                    "updated_at": now,
                }
            },
        )

    return result


async def list_followups_due(followup_after_days: int) -> list[dict]:
    """Applied jobs older than `followup_after_days` that haven't had a reminder sent yet."""
    db = get_db()
    cutoff = datetime.now(timezone.utc).timestamp() - followup_after_days * 86400
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    query = {
        "status": "applied",
        "applied_at": {"$lte": cutoff_dt},
        "reminder_sent_at": None,
    }
    jobs = await db.jobs.find(query).to_list(length=200)
    return [_to_detail(j) for j in jobs]


async def mark_followup_sent(job_id: str) -> dict:
    db = get_db()
    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"reminder_sent_at": datetime.now(timezone.utc)}},
    )
    return await get_job(job_id)


async def analyze_job(job_id: str, resume_id: str | None = None) -> dict:
    job = await get_job(job_id)

    if resume_id:
        resume = await resume_service.get_resume(resume_id)
    else:
        resume = await resume_service.get_default_resume()
        if not resume:
            raise ValueError(
                "No resume specified and no default resume set. "
                "Upload a resume and mark it default, or pass resume_id explicitly."
            )
    resume_text = resume.get("extracted_text", "")
    if not resume_text.strip():
        raise ValueError("Selected resume has no extracted text")

    provider = await get_ai_provider()
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        job_description=job["description"][:8000],
        resume_text=resume_text[:8000],
    )
    raw_result = await provider.generate(prompt, system=ANALYSIS_SYSTEM_PROMPT)

    try:
        parsed = _extract_json(raw_result)
    except (json.JSONDecodeError, AttributeError):
        # AI didn't return clean JSON - fail gracefully instead of crashing,
        # keep the raw text so the user can still see what came back.
        parsed = {
            "extracted_skills": [],
            "responsibilities": [],
            "experience_required": "",
            "salary_range": "",
            "benefits": [],
            "required_keywords": [],
            "match_percent": 0,
            "match_reason": f"Could not parse AI response as JSON. Raw response: {raw_result[:500]}",
            "missing_skills": [],
            "learning_suggestions": [],
            "interview_difficulty": "",
        }

    analysis = {
        "provider": provider.name,
        "analyzed_at": datetime.now(timezone.utc),
        "resume_id": resume["id"],
        **parsed,
    }

    db = get_db()
    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"analysis": analysis, "updated_at": datetime.now(timezone.utc)}},
    )
    return await get_job(job_id)


async def analyze_unanalyzed_jobs(resume_id: str | None = None, limit: int = 15) -> dict:
    """
    Runs AI analysis on up to `limit` jobs that don't have a match score
    yet. Capped (default 15) since each job costs one AI call - useful
    right after a search so a "min match %" filter has real data to
    work with, without silently burning through AI quota on every job
    found automatically.
    """
    candidates = await list_unanalyzed_jobs(limit=limit)
    succeeded, failed = 0, 0
    for job in candidates:
        try:
            await analyze_job(job["id"], resume_id=resume_id)
            succeeded += 1
        except Exception:
            failed += 1
    return {"attempted": len(candidates), "succeeded": succeeded, "failed": failed}


def _to_summary(j: dict) -> dict:
    analysis = j.get("analysis") or {}
    return {
        "id": str(j["_id"]),
        "title": j["title"],
        "company": j["company"],
        "location": j.get("location", ""),
        "source": j.get("source", "manual"),
        "status": j.get("status", "new"),
        "created_at": j["created_at"],
        "updated_at": j["updated_at"],
        "match_percent": analysis.get("match_percent"),
    }


def _to_detail(j: dict) -> dict:
    summary = _to_summary(j)
    summary.update(
        {
            "url": j.get("url", ""),
            "salary_text": j.get("salary_text", ""),
            "description": j.get("description", ""),
            "notes": j.get("notes", ""),
            "analysis": j.get("analysis"),
            "applied_at": j.get("applied_at"),
            "reminder_sent_at": j.get("reminder_sent_at"),
            "application_method": j.get("application_method"),
            "application_email_to": j.get("application_email_to"),
            "hr_email_guess": j.get("hr_email_guess"),
        }
    )
    return summary
