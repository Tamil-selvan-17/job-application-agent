"""
Cover letter management - mirrors resume_service.py but simpler (no
version history, since cover letters are typically swapped out wholesale
rather than iterated on in place). Setting a default keeps
config.default_cover_letter in sync, same as resumes.

File bytes stored directly in Mongo (base64) rather than local disk -
same reason as resume_service.py: Render's free tier wipes the
filesystem on every deploy, which was silently breaking attachments.

AI-generated cover letters (tailored per job) are a separate future
feature - this stage covers upload + storage + default selection only.
"""
from datetime import datetime, timezone
from pathlib import Path
import base64
from bson import ObjectId
from fastapi import UploadFile

from app.database.mongo import get_db
from app.services.resume_parser import extract_text_from_bytes
from app.services import config_service


def _validate_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise ValueError("Only .pdf and .docx cover letters are supported")
    return ext


async def upload_cover_letter(file: UploadFile, is_default: bool = False) -> dict:
    ext = _validate_ext(file.filename)
    db = get_db()

    content = await file.read()
    text = extract_text_from_bytes(content, file.filename)
    content_b64 = base64.b64encode(content).decode("ascii")

    doc = {
        "filename": file.filename,
        "file_type": ext.lstrip("."),
        "is_default": is_default,
        "extracted_text": text,
        "file_content_base64": content_b64,
        "uploaded_at": datetime.now(timezone.utc),
    }
    result = await db.cover_letters.insert_one(doc)
    cl_id = str(result.inserted_id)

    if is_default:
        await set_default_cover_letter(cl_id)

    return await get_cover_letter(cl_id)


async def list_cover_letters() -> list[dict]:
    db = get_db()
    items = await db.cover_letters.find().sort("uploaded_at", -1).to_list(length=200)
    return [_to_summary(c) for c in items]


async def get_cover_letter(cl_id: str) -> dict:
    db = get_db()
    c = await db.cover_letters.find_one({"_id": ObjectId(cl_id)})
    if not c:
        raise ValueError("Cover letter not found")
    return _to_detail(c)


async def get_default_cover_letter() -> dict | None:
    db = get_db()
    c = await db.cover_letters.find_one({"is_default": True})
    return _to_detail(c) if c else None


async def get_cover_letter_file(cl_id: str) -> tuple[bytes, str]:
    """Returns (file_bytes, filename) for attaching the actual file to an email."""
    db = get_db()
    c = await db.cover_letters.find_one({"_id": ObjectId(cl_id)})
    if not c:
        raise ValueError("Cover letter not found")
    b64 = c.get("file_content_base64", "")
    content = base64.b64decode(b64) if b64 else b""
    return content, c.get("filename", "cover_letter")


async def set_default_cover_letter(cl_id: str) -> dict:
    db = get_db()
    await db.cover_letters.update_many({}, {"$set": {"is_default": False}})
    await db.cover_letters.update_one({"_id": ObjectId(cl_id)}, {"$set": {"is_default": True}})
    cover_letter = await get_cover_letter(cl_id)
    await config_service.patch_config({"default_cover_letter": cover_letter["filename"]})
    return cover_letter


async def delete_cover_letter(cl_id: str) -> None:
    db = get_db()
    c = await db.cover_letters.find_one({"_id": ObjectId(cl_id)})
    if not c:
        raise ValueError("Cover letter not found")
    await db.cover_letters.delete_one({"_id": ObjectId(cl_id)})
    if c.get("is_default"):
        await config_service.patch_config({"default_cover_letter": ""})


def _to_summary(c: dict) -> dict:
    text = c.get("extracted_text", "")
    return {
        "id": str(c["_id"]),
        "filename": c["filename"],
        "file_type": c["file_type"],
        "is_default": c.get("is_default", False),
        "uploaded_at": c["uploaded_at"],
        "text_preview": text[:300],
    }


def _to_detail(c: dict) -> dict:
    summary = _to_summary(c)
    summary["extracted_text"] = c.get("extracted_text", "")
    return summary
