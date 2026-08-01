from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.job_model import JobCreate, JobUpdate, JobSummary, JobDetail
from app.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class ApplyEmailRequest(BaseModel):
    hr_email: str
    resume_id: str | None = None
    cover_letter_id: str | None = None
    subject: str | None = None       # optional - override the auto-generated subject
    html_body: str | None = None     # optional - override the auto-generated body (from Preview + edit)


@router.post("", response_model=JobDetail)
async def create_job(job: JobCreate):
    return await job_service.create_job(job.model_dump())


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    status: str | None = Query(None),
    min_match: int | None = Query(None, description="Only return jobs with AI match_percent >= this value. Unanalyzed jobs are excluded when set."),
):
    return await job_service.list_jobs(status=status, min_match=min_match)


@router.delete("/clear")
async def clear_jobs(status: str | None = Query("new", description="Only clear jobs with this status; pass empty/omit for none-filter, or status=all to clear everything")):
    """
    Bulk-delete jobs. Defaults to status=new so anything you've saved/
    applied to/tracked isn't touched. Use status=all to wipe everything
    (e.g. to clear out stale results from before a search-relevance fix).
    """
    effective_status = None if status in (None, "", "all") else status
    deleted = await job_service.clear_jobs(status=effective_status)
    return {"deleted": deleted, "status_filter": effective_status or "all"}


@router.post("/analyze-unanalyzed")
async def analyze_unanalyzed(resume_id: str | None = Query(None), limit: int = Query(15, ge=1, le=50)):
    """
    Runs AI ATS analysis on up to `limit` jobs that don't have a match
    score yet, so a "min match %" filter has real data to work with.
    Capped by default since each job costs one AI call.
    """
    return await job_service.analyze_unanalyzed_jobs(resume_id=resume_id, limit=limit)


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str):
    try:
        return await job_service.get_job(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.put("/{job_id}", response_model=JobDetail)
async def update_job(job_id: str, patch: JobUpdate):
    try:
        return await job_service.update_job(job_id, patch.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    try:
        await job_service.delete_job(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"deleted": True}


@router.post("/{job_id}/analyze", response_model=JobDetail)
async def analyze_job(job_id: str, resume_id: str | None = Query(None)):
    """
    Runs the active AI provider (per .env) to extract skills/responsibilities/
    keywords from the JD and computes an ATS match score against the given
    resume_id, or the default resume if not specified.
    """
    try:
        return await job_service.analyze_job(job_id, resume_id=resume_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{job_id}/resolve-url")
async def resolve_apply_url(job_id: str):
    """
    Follows redirects server-side (e.g. Adzuna's tracking link) and
    returns the final destination URL, so "Apply Now" can open the real
    employer page directly instead of landing on an intermediate
    aggregator page. Falls back to the original URL if resolution fails.
    """
    try:
        url = await job_service.resolve_apply_url(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"url": url}


@router.post("/{job_id}/apply-email/preview")
async def preview_apply_email(job_id: str):
    """Returns the subject+body that would be sent, without sending - for review/editing first."""
    try:
        return await job_service.preview_application_email(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{job_id}/apply-email")
async def apply_via_email(job_id: str, req: ApplyEmailRequest):
    """
    Sends a professional application email to req.hr_email with your
    default (or specified) resume attached, plus cover letter if set.
    Pass subject/html_body (from the /preview endpoint, possibly edited)
    to send exactly that instead of regenerating it. On success, marks
    the job "applied" and records the method for tracking/follow-up
    reminders.
    """
    try:
        result = await job_service.apply_via_email(
            job_id,
            req.hr_email,
            resume_id=req.resume_id,
            cover_letter_id=req.cover_letter_id,
            subject_override=req.subject,
            html_override=req.html_body,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result.get("sent"):
        raise HTTPException(400, result.get("reason", "Failed to send application email"))
    return result
