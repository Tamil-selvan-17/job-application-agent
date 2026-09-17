"""
JD Analysis router.

POST /api/jobs/{job_id}/analyze-jd   — run structured JD analysis
"""
from fastapi import APIRouter, HTTPException
from app.services import agent_orchestrator_service

router = APIRouter(prefix="/api/jobs", tags=["jd-analysis"])


@router.post("/{job_id}/analyze-jd")
async def analyze_jd(job_id: str):
    """
    Runs the enhanced structured JD analysis (hooks, ATS keywords, technologies,
    recruiter signals). Stores the result in job.jd_analysis.
    Different from the existing /analyze endpoint (which does ATS match scoring
    against a resume). This runs even before a resume is generated.
    """
    try:
        return await agent_orchestrator_service.run_jd_analysis(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"JD analysis failed: {e}")
