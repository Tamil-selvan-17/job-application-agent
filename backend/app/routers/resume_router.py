from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from app.models.resume_model import ResumeSummary, ResumeDetail, ResumeVersion, ResumeAnalysis
from app.services import resume_service

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.post("/upload", response_model=ResumeDetail)
async def upload_resume(file: UploadFile = File(...), is_default: bool = Query(False)):
    try:
        return await resume_service.upload_resume(file, is_default=is_default)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[ResumeSummary])
async def list_resumes():
    return await resume_service.list_resumes()


@router.get("/default", response_model=ResumeDetail)
async def get_default_resume():
    resume = await resume_service.get_default_resume()
    if not resume:
        raise HTTPException(404, "No default resume set yet")
    return resume


@router.get("/{resume_id}", response_model=ResumeDetail)
async def get_resume(resume_id: str):
    try:
        return await resume_service.get_resume(resume_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.put("/{resume_id}/default", response_model=ResumeDetail)
async def set_default(resume_id: str):
    try:
        return await resume_service.set_default_resume(resume_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str):
    try:
        await resume_service.delete_resume(resume_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"deleted": True}


@router.post("/{resume_id}/versions", response_model=ResumeDetail)
async def add_version(resume_id: str, file: UploadFile = File(...)):
    try:
        return await resume_service.add_version(resume_id, file)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{resume_id}/versions", response_model=list[ResumeVersion])
async def list_versions(resume_id: str):
    return await resume_service.list_versions(resume_id)


@router.post("/{resume_id}/analyze", response_model=ResumeAnalysis)
async def analyze_resume(resume_id: str):
    """Runs the active AI provider (per .env) over the resume text: skills, ATS suggestions, gaps."""
    try:
        return await resume_service.analyze_resume(resume_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
