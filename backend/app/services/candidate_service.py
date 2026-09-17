"""
Candidate profile service.

Stores and retrieves the single CandidateProfile document from the
`candidate_profiles` collection. There is always at most one document
in this collection (upserted on every save).

Auto-syncs default values from JobSearchConfig (name, email, phone, skills, experience)
and uploaded original DOCX resume template.
"""
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongo import get_db

PROFILE_SINGLETON_KEY = "main"


async def get_profile() -> dict:
    """
    Retrieves the candidate profile document. Auto-enriches missing details
    from JobSearchConfig and default/latest uploaded DOCX resume template.
    """
    db = get_db()
    doc = await db.candidate_profiles.find_one({"_key": PROFILE_SINGLETON_KEY})
    if not doc:
        doc = {"_key": PROFILE_SINGLETON_KEY}

    enriched_doc, modified = await _auto_enrich_profile(doc)
    if modified:
        now = datetime.now(timezone.utc)
        to_save = {**enriched_doc, "_key": PROFILE_SINGLETON_KEY, "updated_at": now}
        to_save.pop("_id", None)
        to_save.pop("id", None)
        await db.candidate_profiles.update_one(
            {"_key": PROFILE_SINGLETON_KEY},
            {"$set": to_save},
            upsert=True,
        )
        doc = await db.candidate_profiles.find_one({"_key": PROFILE_SINGLETON_KEY})

    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    doc.pop("_key", None)
    return doc


async def save_profile(data: dict) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    data.pop("id", None)
    data.pop("_id", None)
    await db.candidate_profiles.update_one(
        {"_key": PROFILE_SINGLETON_KEY},
        {"$set": {**data, "_key": PROFILE_SINGLETON_KEY, "updated_at": now}},
        upsert=True,
    )
    return await get_profile()


async def patch_profile(patch: dict) -> dict:
    """Merge-patch: only update provided keys, leave the rest untouched."""
    db = get_db()
    now = datetime.now(timezone.utc)
    patch.pop("id", None)
    patch.pop("_id", None)

    # Flatten nested dicts for MongoDB dot-notation updates so we don't
    # overwrite sibling keys inside e.g. "personal".
    flat: dict = {}
    for k, v in patch.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v
    flat["updated_at"] = now

    await db.candidate_profiles.update_one(
        {"_key": PROFILE_SINGLETON_KEY},
        {"$set": {**flat, "_key": PROFILE_SINGLETON_KEY}},
        upsert=True,
    )
    return await get_profile()


async def sync_original_resume(resume_id: str) -> None:
    """Explicitly link a DOCX resume as the master template for candidate profile."""
    await patch_profile({"original_resume_id": resume_id})


async def _auto_enrich_profile(doc: dict) -> tuple[dict, bool]:
    """
    Auto-populates candidate profile fields from:
      1. JobSearchConfig (name, email, phone, location, website, skills, experience, preferences)
      2. Uploaded default/latest DOCX resume (original_resume_id)
    Returns (enriched_doc, modified_boolean).
    """
    db = get_db()
    modified = False

    # 1. Fetch JobSearchConfig
    try:
        from app.services import config_service
        config = await config_service.get_config()
    except Exception:
        config = {}

    personal = doc.get("personal") if isinstance(doc.get("personal"), dict) else {}

    # Auto-fill personal details from JobSearchConfig if empty
    if not personal.get("full_name") and config.get("name"):
        personal["full_name"] = config.get("name", "")
        modified = True
    if not personal.get("email") and config.get("email"):
        personal["email"] = config.get("email", "")
        modified = True
    if not personal.get("phone") and config.get("phone"):
        personal["phone"] = config.get("phone", "")
        modified = True
    if not personal.get("location") and config.get("location"):
        personal["location"] = config.get("location", "")
        modified = True
    if not personal.get("website") and config.get("website_link"):
        personal["website"] = config.get("website_link", "")
        modified = True
    doc["personal"] = personal

    career = doc.get("career") if isinstance(doc.get("career"), dict) else {}
    if not career.get("total_experience") and config.get("experience"):
        exp_val = config.get("experience")
        career["total_experience"] = f"{exp_val} years" if str(exp_val).isdigit() else str(exp_val)
        modified = True
    doc["career"] = career

    # Auto-fill skills from config if profile skills is empty
    if not doc.get("skills") and config.get("skills"):
        doc["skills"] = list(config.get("skills", []))
        modified = True

    # Auto-fill preferences from config if empty
    pref = doc.get("preferences") if isinstance(doc.get("preferences"), dict) else {}
    if not pref.get("locations") and config.get("locations"):
        pref["locations"] = list(config.get("locations", []))
        modified = True
    if not pref.get("work_mode") and config.get("work_mode"):
        pref["work_mode"] = list(config.get("work_mode", []))
        modified = True
    if not pref.get("employment_type") and config.get("employment_type"):
        pref["employment_type"] = list(config.get("employment_type", []))
        modified = True
    doc["preferences"] = pref

    # 2. Auto-link original DOCX resume if original_resume_id is missing or invalid
    current_resume_id = doc.get("original_resume_id", "")
    try:
        resume_valid = False
        if current_resume_id:
            try:
                r = await db.resumes.find_one({"_id": ObjectId(current_resume_id)})
                if r:
                    resume_valid = True
            except Exception:
                resume_valid = False

        if not resume_valid:
            # Try default resume first
            default_resume = await db.resumes.find_one({"is_default": True, "file_type": "docx"})
            if not default_resume:
                default_resume = await db.resumes.find_one({"is_default": True})

            if default_resume and default_resume.get("file_type") == "docx":
                doc["original_resume_id"] = str(default_resume["_id"])
                modified = True
            else:
                # Fallback to latest uploaded .docx resume
                latest_docx = await db.resumes.find_one({"file_type": "docx"}, sort=[("uploaded_at", -1)])
                if latest_docx:
                    doc["original_resume_id"] = str(latest_docx["_id"])
                    modified = True
    except Exception:
        pass

    return doc, modified
