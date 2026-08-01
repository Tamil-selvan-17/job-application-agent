from fastapi import APIRouter, HTTPException

from app.services import email_service, job_service, config_service
from app.config.env import env_settings

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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
    config = await config_service.get_config()
    days = int(config.get("followup_after_days", 5))
    return await job_service.list_followups_due(days)


@router.post("/followups/{job_id}/send")
async def send_followup(job_id: str):
    """Sends a follow-up reminder email for a single job now, and marks it as reminded."""
    job = await job_service.get_job(job_id)
    result = await email_service.notify_followups_due([job])
    if result.get("sent"):
        await job_service.mark_followup_sent(job_id)
    return result
