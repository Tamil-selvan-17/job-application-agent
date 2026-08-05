"""
A small set of settings that ARE switchable from the UI without a
redeploy - distinct from AI_PROVIDER itself, which stays .env-only by
deliberate design (per earlier project decision).

Model choice is different: Gemini models get overloaded (503) or hit
per-model rate limits (429) somewhat unpredictably, and each model has
its own separate free-tier quota - so being able to switch models
quickly from the UI, without waiting on a redeploy, has real practical
value. Stored as a single doc in the `settings` collection, with the
.env value as the default when no override is set.
"""
from app.database.mongo import get_db

RUNTIME_SETTINGS_DOC_ID = "runtime_overrides"


async def get_overrides() -> dict:
    db = get_db()
    doc = await db.settings.find_one({"_id": RUNTIME_SETTINGS_DOC_ID})
    return doc or {}


async def set_override(key: str, value: str) -> dict:
    db = get_db()
    await db.settings.update_one(
        {"_id": RUNTIME_SETTINGS_DOC_ID},
        {"$set": {key: value}},
        upsert=True,
    )
    return await get_overrides()
