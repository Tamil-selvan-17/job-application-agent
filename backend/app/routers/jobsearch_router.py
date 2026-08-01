from fastapi import APIRouter

from app.services import job_search_service
from app.services.job_sources import SOURCE_FETCHERS, UNIMPLEMENTED_SOURCES

router = APIRouter(prefix="/api/jobsearch", tags=["job search"])


@router.post("/run")
async def run_search():
    """Manually trigger a job search across the sources set in your Job Search Config."""
    return await job_search_service.search_and_store_jobs()


@router.get("/sources")
async def list_sources():
    return {
        "implemented": sorted(SOURCE_FETCHERS.keys()),
        "not_yet_implemented": sorted(UNIMPLEMENTED_SOURCES),
        "note": (
            "Implemented sources are free public job-board APIs (no login/scraping). "
            "LinkedIn/Indeed/Naukri/etc. require browser automation (Playwright) with "
            "login/session/CAPTCHA handling - a separate, higher-risk future stage."
        ),
    }
