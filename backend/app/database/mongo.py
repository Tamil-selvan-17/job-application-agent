"""
Single shared MongoDB (motor) client for the whole app.

Collections used across the app (created lazily, no fixed schema needed):
users, resumes, resumes_versions, jobs, companies, applications,
interviews, reminders, skills, embeddings, browser_sessions, prompts,
email_templates, activity_logs, settings, ai_history, job_configs
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config.env import env_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(env_settings.mongo_uri)
    _db = _client[env_settings.mongo_db_name]


def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        # Allow lazy connect if startup event hasn't fired yet (e.g. in tests/scripts)
        connect_to_mongo()
    return _db
