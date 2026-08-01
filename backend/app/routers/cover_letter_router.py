from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from app.models.cover_letter_model import CoverLetterSummary, CoverLetterDetail
from app.services import cover_letter_service

router = APIRouter(prefix="/api/cover-letters", tags=["cover letters"])


@router.post("/upload", response_model=CoverLetterDetail)
async def upload_cover_letter(file: UploadFile = File(...), is_default: bool = Query(False)):
    try:
        return await cover_letter_service.upload_cover_letter(file, is_default=is_default)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[CoverLetterSummary])
async def list_cover_letters():
    return await cover_letter_service.list_cover_letters()


@router.get("/default", response_model=CoverLetterDetail)
async def get_default_cover_letter():
    cl = await cover_letter_service.get_default_cover_letter()
    if not cl:
        raise HTTPException(404, "No default cover letter set yet")
    return cl


@router.get("/{cl_id}", response_model=CoverLetterDetail)
async def get_cover_letter(cl_id: str):
    try:
        return await cover_letter_service.get_cover_letter(cl_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.put("/{cl_id}/default", response_model=CoverLetterDetail)
async def set_default(cl_id: str):
    try:
        return await cover_letter_service.set_default_cover_letter(cl_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{cl_id}")
async def delete_cover_letter(cl_id: str):
    try:
        await cover_letter_service.delete_cover_letter(cl_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"deleted": True}
