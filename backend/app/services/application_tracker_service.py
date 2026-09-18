"""
Application tracking service.

Manages the `applications` and `generated_resumes` Mongo collections.

Key responsibilities:
- Create / update application records
- Deduplication guard: has this job already been applied to?
- Store generated DOCX/PDF as base64 in generated_resumes
- Schedule cleanup: delete DOCX/PDF 1 day after application marked APPLIED
- Query dashboard stats

File lifecycle:
  generated_resumes document created  →  job applied  →  scheduled_delete_at = now+1day
  → daily scheduler deletes documents where scheduled_delete_at < now
"""
import base64
from datetime import datetime, timedelta, timezone
from bson import ObjectId

from app.database.mongo import get_db


# --------------------------------------------------------------------------- #
#  Generated Resume documents                                                  #
# --------------------------------------------------------------------------- #

async def store_generated_resume(
    job_id: str,
    job_title: str,
    company: str,
    docx_bytes: bytes,
    pdf_bytes: bytes,
    docx_filename: str,
    pdf_filename: str,
    ats_score: int,
    ats_analysis: dict,
    customization_summary: list[str],
    hooks_used: list[str],
    cover_letter_pdf_bytes: bytes | None = None,
    cover_letter_filename: str | None = None,
) -> str:
    """Stores DOCX + PDF as base64. Returns the generated_resume _id string."""
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "docx_filename": docx_filename,
        "pdf_filename": pdf_filename,
        "docx_base64": base64.b64encode(docx_bytes).decode("ascii"),
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "cover_letter_pdf_base64": base64.b64encode(cover_letter_pdf_bytes).decode("ascii") if cover_letter_pdf_bytes else None,
        "cover_letter_filename": cover_letter_filename,
        "ats_score": ats_score,
        "ats_analysis": ats_analysis,
        "customization_summary": customization_summary,
        "hooks_used": hooks_used,
        "created_at": now,
        "applied_at": None,
        "scheduled_delete_at": now + timedelta(days=1),
    }
    result = await db.generated_resumes.insert_one(doc)
    return str(result.inserted_id)


async def get_generated_resume(resume_id: str) -> dict | None:
    db = get_db()
    doc = await db.generated_resumes.find_one({"_id": ObjectId(resume_id)})
    if not doc:
        return None
    return _resume_to_dict(doc)


async def get_generated_resume_for_job(job_id: str) -> dict | None:
    """Get the most recent generated resume for a job (if any)."""
    db = get_db()
    doc = await db.generated_resumes.find_one(
        {"job_id": job_id},
        sort=[("created_at", -1)],
    )
    return _resume_to_dict(doc) if doc else None


async def get_generated_resume_bytes(resume_id: str) -> tuple[bytes, bytes, str, str, bytes | None, str | None]:
    """Returns (docx_bytes, pdf_bytes, docx_filename, pdf_filename, cover_letter_pdf_bytes, cover_letter_filename)."""
    db = get_db()
    doc = await db.generated_resumes.find_one({"_id": ObjectId(resume_id)})
    if not doc:
        raise ValueError("Generated resume not found")
    docx = base64.b64decode(doc.get("docx_base64", "")) if doc.get("docx_base64") else b""
    pdf = base64.b64decode(doc.get("pdf_base64", "")) if doc.get("pdf_base64") else b""
    cl_pdf = base64.b64decode(doc.get("cover_letter_pdf_base64", "")) if doc.get("cover_letter_pdf_base64") else None
    cl_fn = doc.get("cover_letter_filename")
    return docx, pdf, doc.get("docx_filename", "resume.docx"), doc.get("pdf_filename", "resume.pdf"), cl_pdf, cl_fn


async def mark_resume_applied(resume_id: str) -> None:
    """Mark the resume as used in an application; schedule deletion in 1 day."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.generated_resumes.update_one(
        {"_id": ObjectId(resume_id)},
        {"$set": {"applied_at": now, "scheduled_delete_at": now + timedelta(days=1)}},
    )


async def cleanup_expired_resumes() -> int:
    """Delete generated_resumes whose scheduled_delete_at is in the past or created >24h ago.
    Called daily by the scheduler or on dashboard load. Returns the number of documents deleted."""
    db = get_db()
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    result = await db.generated_resumes.delete_many(
        {
            "$or": [
                {"scheduled_delete_at": {"$lte": now, "$ne": None}},
                {"created_at": {"$lte": one_day_ago}}
            ]
        }
    )
    return result.deleted_count


def _resume_to_dict(doc: dict) -> dict:
    d = {k: v for k, v in doc.items() if k not in ("docx_base64", "pdf_base64", "cover_letter_pdf_base64")}
    d["id"] = str(d.pop("_id"))
    return d


# --------------------------------------------------------------------------- #
#  Application records                                                         #
# --------------------------------------------------------------------------- #

async def create_application(
    job_id: str,
    company: str,
    role: str,
    application_url: str,
    generated_resume_id: str,
    ats_score: int,
    method: str = "email",
) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "job_id": job_id,
        "company": company,
        "role": role,
        "application_url": application_url,
        "generated_resume_id": generated_resume_id,
        "ats_score": ats_score,
        "method": method,
        "email_sent": False,
        "email_sent_at": None,
        "email_to": "",
        "website_applied": False,
        "applied_at": None,
        "status": "PENDING",
        "error": None,
        "screenshot_path": None,
        "failed_step": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.applications.insert_one(doc)
    return await get_application(str(result.inserted_id))


async def update_application(app_id: str, patch: dict) -> dict:
    db = get_db()
    patch["updated_at"] = datetime.now(timezone.utc)
    await db.applications.update_one({"_id": ObjectId(app_id)}, {"$set": patch})
    return await get_application(app_id)


async def get_application(app_id: str) -> dict:
    db = get_db()
    doc = await db.applications.find_one({"_id": ObjectId(app_id)})
    if not doc:
        raise ValueError("Application not found")
    return _app_to_dict(doc)


async def get_application_for_job(job_id: str) -> dict | None:
    db = get_db()
    doc = await db.applications.find_one({"job_id": job_id}, sort=[("created_at", -1)])
    return _app_to_dict(doc) if doc else None


async def list_applications(status: str | None = None) -> list[dict]:
    db = get_db()
    query = {"status": status} if status else {}
    apps = await db.applications.find(query).sort("created_at", -1).to_list(length=500)
    return [_app_to_dict(a) for a in apps]


async def check_duplicate_application(job_id: str) -> bool:
    """Returns True if this job has already been successfully applied to."""
    db = get_db()
    existing = await db.applications.find_one(
        {"job_id": job_id, "status": {"$in": ["APPLIED", "EMAIL_SENT"]}}
    )
    return existing is not None


async def get_dashboard_stats() -> dict:
    db = get_db()
    await cleanup_expired_resumes()

    app_applied = await db.applications.count_documents({"status": "APPLIED"})
    app_email_sent = await db.applications.count_documents({"status": "EMAIL_SENT"})
    app_pending = await db.applications.count_documents({"status": "PENDING"})
    app_failed = await db.applications.count_documents({"status": "FAILED"})

    job_applied = await db.jobs.count_documents({"status": {"$in": ["applied", "APPLIED"]}})
    job_email_sent = await db.jobs.count_documents({"status": {"$in": ["email_sent", "EMAIL_SENT"]}})
    job_pending = await db.jobs.count_documents({"status": {"$in": ["pending", "PENDING", "new", "NEW"]}})
    job_failed = await db.jobs.count_documents({"status": {"$in": ["failed", "FAILED", "rejected", "REJECTED"]}})
    job_resume_ready = await db.jobs.count_documents({"$or": [{"status": "resume_ready"}, {"resume_status": "READY"}]})

    resumes_count = await db.generated_resumes.count_documents({})

    applied = max(app_applied, job_applied)
    email_sent = max(app_email_sent, job_email_sent)
    pending = max(app_pending, job_pending)
    failed = max(app_failed, job_failed)
    resume_ready = max(resumes_count, job_resume_ready)

    total_apps = await db.applications.count_documents({})
    total_jobs = await db.jobs.count_documents({})
    total = max(total_apps, total_jobs, applied + email_sent + pending + failed + resume_ready)

    return {
        "total": total,
        "total_applied": applied,
        "applied": applied,
        "email_sent": email_sent,
        "emails_sent": email_sent,
        "pending": pending,
        "pending_applications": pending,
        "failed": failed,
        "rejected": failed,
        "resume_ready": resume_ready,
        "resumes_generated": resume_ready,
    }


def _app_to_dict(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d
