"""
Candidate profile service.

Stores and retrieves the single CandidateProfile document from the
`candidate_profiles` collection. There is always at most one document
in this collection (upserted on every save).

Does NOT touch any existing collection (resumes, jobs, config, etc.).
"""
from datetime import datetime, timezone
from app.database.mongo import get_db

PROFILE_SINGLETON_KEY = "main"


async def get_profile() -> dict:
    db = get_db()
    doc = await db.candidate_profiles.find_one({"_key": PROFILE_SINGLETON_KEY})
    if not doc:
        return {}
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
