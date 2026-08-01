"""
Base environment configuration.
These are the *startup defaults*. Anything here (except secrets) can be
overridden at runtime from the Settings page in the UI - overrides are
persisted in MongoDB (see services/settings_service.py) and take priority
over these env defaults without requiring a restart or code change.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "job_agent"

    # AI provider defaults (overridable at runtime via UI)
    ai_provider: str = "ollama"  # "ollama" | "gemini"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # App
    app_env: str = "development"
    upload_dir: str = "uploads"

    # Adzuna (https://developer.adzuna.com/) - free, keyed job-search API
    # that actually indexes India (and most other countries) - unlike
    # Remotive/Arbeitnow, which are almost entirely Western remote-job
    # boards. Sign up free, then set these to enable it as a source.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"  # ISO country code Adzuna searches, e.g. "in", "gb", "us"

    # Email notifications. EMAIL_PROVIDER options: "brevo" (recommended -
    # genuinely permanent free plan, no domain needed), "sendgrid" (now a
    # 60-day trial only, not permanent), or "smtp" (local dev / paid
    # Render plans - Render's free tier blocks outbound SMTP ports
    # entirely). Leave the matching *_api_key/smtp_host empty to disable
    # emails - notification calls just no-op with a clear message.
    email_provider: str = "brevo"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_email_to: str = ""  # falls back to the "email" field in the job-search config if empty

    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""  # must match your Single Sender Verified address
    sendgrid_from_name: str = ""

    # Brevo (https://www.brevo.com) - genuinely permanent free plan (300
    # emails/day, no trial expiry, unlike SendGrid which now expires
    # after 60 days). Sender verification is just a 6-digit code emailed
    # to you - no custom domain/DNS required. Recommended default for
    # Render's free tier.
    brevo_api_key: str = ""
    brevo_from_email: str = ""  # must match your verified sender
    brevo_from_name: str = ""

    # Scheduler
    enable_scheduler: bool = True
    daily_search_hour_utc: int = 3   # runs once a day at this UTC hour
    daily_reminder_hour_utc: int = 4


env_settings = EnvSettings()
