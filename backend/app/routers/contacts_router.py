"""
HR Contact Discovery router.

POST /api/jobs/{job_id}/find-contacts — run contact discovery
GET  /api/jobs/{job_id}/contacts      — list discovered contacts
"""
from fastapi import APIRouter, HTTPException
from app.services import contact_finder_service
from app.services.job_service import get_job

router = APIRouter(prefix="/api/jobs", tags=["contacts"])


@router.post("/{job_id}/find-contacts")
async def find_contacts(job_id: str):
    """
    Searches public sources (JD text, company website) for HR/recruiter email contacts.
    Stores results in job.contacts and updates workflow_state to CONTACTS_FOUND.
    """
    try:
        contacts = await contact_finder_service.discover_and_store_contacts(job_id)
        return {"job_id": job_id, "contacts_found": len(contacts), "contacts": contacts}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Contact discovery failed: {e}")


@router.get("/{job_id}/contacts")
async def get_contacts(job_id: str):
    """Returns the contacts already discovered for this job."""
    try:
        job = await get_job(job_id)
        return {"job_id": job_id, "contacts": job.get("contacts", [])}
    except ValueError as e:
        raise HTTPException(404, str(e))
