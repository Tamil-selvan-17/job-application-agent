from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import email_service, job_service
from app.config.env import env_settings

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class SendFollowupRequest(BaseModel):
    subject: str | None = None     # optional - override the auto-generated subject (from /preview, possibly edited)
    html_body: str | None = None   # optional - override the auto-generated body


@router.get("/status")
async def status():
    return {"configured": email_service.is_configured(), "provider": env_settings.email_provider}


@router.post("/test-email")
async def test_email():
    result = await email_service.send_email(
        "AI Job Application Agent - test email",
        "<p>If you're reading this, email notifications are working. ✅</p>",
    )
    if not result.get("sent"):
        raise HTTPException(400, result.get("reason", "Failed to send"))
    return result


@router.get("/followups/due")
async def followups_due():
    """
    Applied jobs where a reminder stage (1st/day 3, 2nd/day 5, 3rd/day 8)
    is due and hasn't been sent yet. Each entry includes
    `next_reminder_stage`. Jobs past day 10 with no reply are
    auto-marked "not_responded" by the daily scheduler rather than
    appearing here indefinitely.
    """
    return await job_service.list_followups_due()


@router.post("/followups/{job_id}/preview")
async def preview_followup(job_id: str, stage: int | None = Query(None)):
    """
    Returns the follow-up email's subject+body without sending, for
    review/editing first. If `stage` isn't given, uses whichever stage
    is next due for this job (defaults to 1st if none is currently due).
    """
    if stage is None:
        due = await job_service.list_followups_due()
        match = next((d for d in due if d["id"] == job_id), None)
        stage = match["next_reminder_stage"] if match else 1
    return await job_service.preview_followup_email(job_id, stage)


@router.post("/followups/{job_id}/send")
async def send_followup(job_id: str, req: SendFollowupRequest = SendFollowupRequest()):
    """
    Sends the next-due reminder stage for a single job now (to its HR
    email if one is on file, otherwise notifies you instead), and marks
    that stage as sent. Pass subject/html_body (from /preview, possibly
    edited) to send exactly that instead of regenerating it.
    """
    job = await job_service.get_job(job_id)
    due = await job_service.list_followups_due()
    match = next((d for d in due if d["id"] == job_id), None)
    stage = match["next_reminder_stage"] if match else 1

    result = await email_service.notify_followup_stage(
        job, stage, subject_override=req.subject, html_override=req.html_body
    )
    if result.get("sent"):
        await job_service.mark_followup_sent(job_id, stage)
    return result


@router.post("/followups/run-all")
async def run_all_followups():
    """Manually triggers the full daily follow-up cycle now (normally runs automatically once a day)."""
    return await job_service.process_followup_reminders()
