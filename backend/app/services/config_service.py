"""
Stores the user's job-search JSON config in Mongo (`settings` collection,
doc _id="job_config"). The UI can GET the current config, PATCH individual
fields, or POST a whole new JSON file to replace it - at any time, no
restart needed.
"""
from app.database.mongo import get_db
from app.models.config_model import JobSearchConfig

CONFIG_DOC_ID = "job_config"


async def get_config() -> dict:
    db = get_db()
    doc = await db.settings.find_one({"_id": CONFIG_DOC_ID})
    if not doc:
        default = JobSearchConfig().model_dump()
        default["_id"] = CONFIG_DOC_ID
        await db.settings.insert_one(default)
        default.pop("_id")
        return default
    doc.pop("_id", None)
    return doc


async def replace_config(new_config: dict) -> dict:
    """Full replace - used when the user uploads a brand new JSON file."""
    validated = JobSearchConfig(**new_config).model_dump()
    db = get_db()
    doc = {"_id": CONFIG_DOC_ID, **validated}
    await db.settings.replace_one({"_id": CONFIG_DOC_ID}, doc, upsert=True)
    validated_copy = doc.copy()
    validated_copy.pop("_id")
    return validated_copy


async def patch_config(patch: dict) -> dict:
    """Partial update - used when the user edits a field or two in the UI."""
    current = await get_config()
    current.update({k: v for k, v in patch.items() if v is not None})
    return await replace_config(current)
