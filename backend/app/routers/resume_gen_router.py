"""
Resume generation API.

POST /api/jobs/{job_id}/customize-resume  — run AI customization + DOCX + PDF
GET  /api/jobs/{job_id}/resume-status     — check current resume status
GET  /api/jobs/{job_id}/preview-pdf       — stream PDF bytes for in-browser preview
GET  /api/jobs/{job_id}/download-pdf      — download PDF
GET  /api/jobs/{job_id}/download-docx     — download DOCX
GET  /api/jobs/{job_id}/resume-info       — metadata (ats_score, filenames, summary)
"""
import io
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import agent_orchestrator_service, application_tracker_service
from app.services.job_service import get_job

router = APIRouter(prefix="/api/jobs", tags=["resume-generation"])


class CustomizeRequest(BaseModel):
    force_regenerate: bool = False


@router.post("/{job_id}/customize-resume")
async def customize_resume(job_id: str, req: CustomizeRequest = CustomizeRequest()):
    """
    Runs full AI customization + DOCX + PDF generation.
    If an existing resume with ATS >= 90% exists, returns it without regenerating
    (unless force_regenerate=true).
    """
    try:
        result = await agent_orchestrator_service.run_resume_pipeline(
            job_id, force_regenerate=req.force_regenerate
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Resume generation failed: {e}")


@router.get("/{job_id}/resume-info")
async def get_resume_info(job_id: str):
    """Get metadata about the generated resume for this job (no file bytes)."""
    try:
        resume = await application_tracker_service.get_generated_resume_for_job(job_id)
        if not resume:
            return {"available": False}
        return {"available": True, **resume}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{job_id}/preview-pdf")
async def preview_pdf(job_id: str):
    """
    Stream the generated PDF for inline browser preview (iframe/embed).
    Returns Content-Disposition: inline so the browser renders it, not downloads it.
    """
    try:
        job = await get_job(job_id)
        resume_id = job.get("generated_resume_id")
        if not resume_id:
            raise HTTPException(404, "No generated resume found. Please generate a resume first.")

        _, pdf_bytes, _, pdf_filename, *rest = await application_tracker_service.get_generated_resume_bytes(resume_id)
        if not pdf_bytes:
            raise HTTPException(404, "PDF file content not found. Please regenerate.")

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{pdf_filename}"'},
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{job_id}/download-pdf")
async def download_pdf(job_id: str):
    """Force-download the generated PDF resume."""
    try:
        job = await get_job(job_id)
        resume_id = job.get("generated_resume_id")
        if not resume_id:
            raise HTTPException(404, "No generated resume found.")

        _, pdf_bytes, _, pdf_filename, *rest = await application_tracker_service.get_generated_resume_bytes(resume_id)
        if not pdf_bytes:
            raise HTTPException(404, "PDF content missing. Please regenerate.")

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'},
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{job_id}/download-docx")
async def download_docx(job_id: str):
    """Force-download the generated DOCX resume."""
    try:
        job = await get_job(job_id)
        resume_id = job.get("generated_resume_id")
        if not resume_id:
            raise HTTPException(404, "No generated resume found.")

        docx_bytes, _, docx_filename, _, *rest = await application_tracker_service.get_generated_resume_bytes(resume_id)
        if not docx_bytes:
            raise HTTPException(404, "DOCX content missing. Please regenerate.")

        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{docx_filename}"'},
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{job_id}/download-cover-letter")
async def download_cover_letter(job_id: str):
    """Force-download the generated Cover Letter PDF."""
    try:
        job = await get_job(job_id)
        resume_id = job.get("generated_resume_id")
        if not resume_id:
            raise HTTPException(404, "No generated resume found.")

        *_, cl_bytes, cl_filename = await application_tracker_service.get_generated_resume_bytes(resume_id)
        if not cl_bytes:
            raise HTTPException(404, "Cover letter PDF content missing. Please regenerate.")

        return StreamingResponse(
            io.BytesIO(cl_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{cl_filename or "Cover_Letter.pdf"}"'},
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
