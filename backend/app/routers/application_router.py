"""
Application tracking router.

GET /api/applications              — list all application records
GET /api/applications/stats        — dashboard statistics
GET /api/applications/{app_id}     — get single application record

Personalized email application endpoint:
POST /api/jobs/{job_id}/apply-email-personalized   — send personalized AI email
POST /api/jobs/{job_id}/apply-email-personalized/preview — preview email
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.services import application_tracker_service, agent_orchestrator_service

router = APIRouter(tags=["applications"])
job_router = APIRouter(prefix="/api/jobs", tags=["applications"])


# --------------------------------------------------------------------------- #
#  Application Records                                                         #
# --------------------------------------------------------------------------- #

@router.get("/api/applications/stats")
async def get_stats():
    return await application_tracker_service.get_dashboard_stats()


@router.get("/api/applications")
async def list_applications(status: str | None = Query(None)):
    return await application_tracker_service.list_applications(status=status)


@router.get("/api/applications/{app_id}")
async def get_application(app_id: str):
    try:
        return await application_tracker_service.get_application(app_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# --------------------------------------------------------------------------- #
#  Personalized Email Application (replaces basic apply-email)                 #
# --------------------------------------------------------------------------- #

class PersonalizedEmailRequest(BaseModel):
    hr_email: str
    generated_resume_id: str | None = None
    subject: str | None = None
    html_body: str | None = None


@job_router.post("/{job_id}/apply-email-personalized/preview")
async def preview_personalized_email(job_id: str):
    """Preview the personalized email that would be sent, without sending."""
    from app.services import candidate_service, config_service
    from app.services.job_service import get_job
    from app.services.agent_orchestrator_service import _build_personalized_email_html

    try:
        job = await get_job(job_id)
        config = await config_service.get_config()
        profile = await candidate_service.get_profile()
        jd_analysis = job.get("jd_analysis", {})
        html = _build_personalized_email_html(job, config, profile, jd_analysis)
        personal = profile.get("personal", {})
        candidate_name = personal.get("full_name", "") or config.get("name", "Candidate")
        subject = f"Application for {job.get('title', 'Open Position')} – {candidate_name}"
        best_contact = ""
        contacts = job.get("contacts", [])
        if contacts:
            best_contact = contacts[0].get("email", "")
        return {"subject": subject, "html_body": html, "suggested_hr_email": best_contact}
    except ValueError as e:
        raise HTTPException(400, str(e))


@job_router.post("/{job_id}/apply-email-personalized")
async def send_personalized_email(job_id: str, req: PersonalizedEmailRequest):
    """
    Sends personalized application email with the generated PDF attached.
    Prevents duplicate applications.
    """
    try:
        result = await agent_orchestrator_service.run_email_application(
            job_id=job_id,
            hr_email=req.hr_email,
            subject_override=req.subject,
            html_override=req.html_body,
            generated_resume_id=req.generated_resume_id,
        )
        if not result.get("sent") and not result.get("duplicate"):
            raise HTTPException(400, result.get("reason", "Failed to send email"))
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
