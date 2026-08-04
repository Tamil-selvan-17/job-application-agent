"""
Resume management: upload (PDF/DOCX), text extraction, version history,
default-resume selection, and AI-powered resume analysis (skills found,
ATS-style improvement suggestions).

File bytes are stored directly in Mongo (base64, `file_content_base64`
field) rather than on local disk. This matters: Render's free tier
wipes the filesystem on every deploy, which was silently breaking
resume/cover-letter attachments in application emails - the DB record
survived, the actual file on disk didn't, and the attach step just
skipped the missing file without erroring. Mongo Atlas persists
independently of app deploys, so this fixes it properly rather than
just working around it. Resumes/cover letters are small (KB, not MB),
well within a single document's 16MB limit.
"""
from datetime import datetime, timezone
import base64
from bson import ObjectId
from fastapi import UploadFile

from app.database.mongo import get_db
from app.services.resume_parser import extract_text_from_bytes
from app.services.ai_provider import get_ai_provider
from app.services import config_service

RESUME_ANALYSIS_PROMPT = """You are an expert ATS (Applicant Tracking System) and resume reviewer.
Given the resume text below, respond with:
1. A list of key skills/technologies detected
2. 3-6 concrete suggestions to improve ATS compatibility and clarity
3. Any obvious gaps (missing sections like summary, quantifiable achievements, etc.)

Resume text:
---
{resume_text}
---
"""


def _validate_ext(filename: str) -> str:
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise ValueError("Only .pdf and .docx resumes are supported")
    return ext


async def upload_resume(file: UploadFile, is_default: bool = False) -> dict:
    ext = _validate_ext(file.filename)
    db = get_db()

    content = await file.read()
    text = extract_text_from_bytes(content, file.filename)
    content_b64 = base64.b64encode(content).decode("ascii")

    now = datetime.now(timezone.utc)
    doc = {
        "filename": file.filename,
        "file_type": ext.lstrip("."),
        "is_default": is_default,
        "current_version": 1,
        "extracted_text": text,
        "file_content_base64": content_b64,
        "uploaded_at": now,
        "updated_at": now,
    }
    result = await db.resumes.insert_one(doc)
    resume_id = str(result.inserted_id)

    await db.resumes_versions.insert_one(
        {
            "resume_id": resume_id,
            "version": 1,
            "filename": file.filename,
            "file_content_base64": content_b64,
            "extracted_text": text,
            "created_at": now,
        }
    )

    if is_default:
        await set_default_resume(resume_id)

    return await get_resume(resume_id)


async def add_version(resume_id: str, file: UploadFile) -> dict:
    ext = _validate_ext(file.filename)
    db = get_db()
    resume = await db.resumes.find_one({"_id": ObjectId(resume_id)})
    if not resume:
        raise ValueError("Resume not found")

    content = await file.read()
    text = extract_text_from_bytes(content, file.filename)
    content_b64 = base64.b64encode(content).decode("ascii")

    new_version = resume["current_version"] + 1
    now = datetime.now(timezone.utc)

    await db.resumes_versions.insert_one(
        {
            "resume_id": resume_id,
            "version": new_version,
            "filename": file.filename,
            "file_content_base64": content_b64,
            "extracted_text": text,
            "created_at": now,
        }
    )

    await db.resumes.update_one(
        {"_id": ObjectId(resume_id)},
        {
            "$set": {
                "current_version": new_version,
                "filename": file.filename,
                "file_type": ext.lstrip("."),
                "extracted_text": text,
                "file_content_base64": content_b64,
                "updated_at": now,
            }
        },
    )
    return await get_resume(resume_id)


async def list_resumes() -> list[dict]:
    db = get_db()
    resumes = await db.resumes.find().sort("uploaded_at", -1).to_list(length=200)
    return [_to_summary(r) for r in resumes]


async def get_resume(resume_id: str) -> dict:
    db = get_db()
    r = await db.resumes.find_one({"_id": ObjectId(resume_id)})
    if not r:
        raise ValueError("Resume not found")
    return _to_detail(r)


async def get_default_resume() -> dict | None:
    db = get_db()
    r = await db.resumes.find_one({"is_default": True})
    return _to_detail(r) if r else None


async def get_resume_file(resume_id: str) -> tuple[bytes, str]:
    """Returns (file_bytes, filename) for attaching the actual file to an email."""
    db = get_db()
    r = await db.resumes.find_one({"_id": ObjectId(resume_id)})
    if not r:
        raise ValueError("Resume not found")
    b64 = r.get("file_content_base64", "")
    content = base64.b64decode(b64) if b64 else b""
    return content, r.get("filename", "resume")


async def set_default_resume(resume_id: str) -> dict:
    db = get_db()
    await db.resumes.update_many({}, {"$set": {"is_default": False}})
    await db.resumes.update_one(
        {"_id": ObjectId(resume_id)}, {"$set": {"is_default": True}}
    )
    resume = await get_resume(resume_id)
    # Keep the Job Search Config JSON in sync - "default_resume" there is
    # derived from this selection, not meant to be hand-typed.
    await config_service.patch_config({"default_resume": resume["filename"]})
    return resume


async def delete_resume(resume_id: str) -> None:
    db = get_db()
    resume = await db.resumes.find_one({"_id": ObjectId(resume_id)})
    if not resume:
        raise ValueError("Resume not found")

    await db.resumes_versions.delete_many({"resume_id": resume_id})
    await db.resumes.delete_one({"_id": ObjectId(resume_id)})

    if resume.get("is_default"):
        await config_service.patch_config({"default_resume": ""})


async def list_versions(resume_id: str) -> list[dict]:
    db = get_db()
    versions = await db.resumes_versions.find({"resume_id": resume_id}).sort("version", -1).to_list(length=200)
    return [
        {
            "id": str(v["_id"]),
            "resume_id": v["resume_id"],
            "version": v["version"],
            "filename": v["filename"],
            "created_at": v["created_at"],
            "extracted_text": v.get("extracted_text", ""),
        }
        for v in versions
    ]


async def analyze_resume(resume_id: str) -> dict:
    resume = await get_resume(resume_id)
    text = resume.get("extracted_text", "")
    if not text.strip():
        raise ValueError("No extracted text available for this resume")

    provider = await get_ai_provider()
    prompt = RESUME_ANALYSIS_PROMPT.format(resume_text=text[:12000])  # guard against huge resumes
    result_text = await provider.generate(prompt)

    db = get_db()
    analyzed_at = datetime.now(timezone.utc)
    await db.ai_history.insert_one(
        {
            "type": "resume_analysis",
            "resume_id": resume_id,
            "provider": provider.name,
            "analyzed_at": analyzed_at,
            "result_text": result_text,
        }
    )

    return {
        "resume_id": resume_id,
        "provider": provider.name,
        "analyzed_at": analyzed_at,
        "result_text": result_text,
    }


def _to_summary(r: dict) -> dict:
    text = r.get("extracted_text", "")
    return {
        "id": str(r["_id"]),
        "filename": r["filename"],
        "file_type": r["file_type"],
        "is_default": r.get("is_default", False),
        "current_version": r.get("current_version", 1),
        "uploaded_at": r["uploaded_at"],
        "updated_at": r["updated_at"],
        "text_preview": text[:300],
    }


def _to_detail(r: dict) -> dict:
    summary = _to_summary(r)
    summary["extracted_text"] = r.get("extracted_text", "")
    return summary
