"""
Browser automation router — Selenium "Apply on Website" workflow.

POST /api/jobs/{job_id}/apply-website             — start browser agent
GET  /api/jobs/{job_id}/apply-website/status      — poll automation status
POST /api/jobs/{job_id}/apply-website/continue    — continue after CAPTCHA
POST /api/jobs/{job_id}/apply-website/confirm     — user confirms, submit form
POST /api/jobs/{job_id}/apply-website/cancel      — cancel automation
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services import agent_orchestrator_service, browser_agent_service

router = APIRouter(prefix="/api/jobs", tags=["browser-agent"])


class StartApplicationRequest(BaseModel):
    generated_resume_id: str | None = None


@router.post("/{job_id}/apply-website")
async def start_website_application(job_id: str, req: StartApplicationRequest = StartApplicationRequest()):
    """
    Starts the Selenium browser agent. Opens Chrome (visible), navigates to
    the application URL, fills the form, and waits for user confirmation.
    """
    try:
        result = await agent_orchestrator_service.start_website_application(
            job_id, generated_resume_id=req.generated_resume_id
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Browser automation failed: {e}")


@router.get("/{job_id}/apply-website/status")
async def get_application_status(job_id: str):
    """Poll the current status of an active browser automation session."""
    state = browser_agent_service.get_session_state(job_id)
    if not state:
        return {"status": "NO_SESSION", "message": "No active browser session for this job."}
    return state


@router.post("/{job_id}/apply-website/continue")
async def continue_after_captcha(job_id: str):
    """
    Called after user completes a CAPTCHA manually in the open browser.
    Checks if CAPTCHA is resolved and moves to AWAITING_CONFIRMATION.
    """
    session = browser_agent_service.get_session(job_id)
    if not session:
        raise HTTPException(404, "No active session found.")
    import asyncio
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, session.continue_after_captcha)
    return {
        "status": state.status,
        "current_step": state.current_step,
        "screenshot_b64": state.screenshot_b64,
        "error": state.error,
    }


@router.post("/{job_id}/apply-website/confirm")
async def confirm_application(job_id: str):
    """
    User has reviewed the filled form and clicks 'Confirm & Submit'.
    Clicks the submit button, updates job status to APPLIED.
    """
    try:
        result = await agent_orchestrator_service.confirm_website_application(job_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{job_id}/apply-website/cancel")
async def cancel_application(job_id: str):
    """Cancels browser automation, closes Chrome, cleans up temp files."""
    return await agent_orchestrator_service.cancel_website_application(job_id)
