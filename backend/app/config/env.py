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

    # Email notifications. EMAIL_PROVIDER options: "mailjet" (recommended
    # - permanent free plan, works immediately, no approval wait),
    # "custom" (self-hosted relay you control - sends SMTP creds + email
    # content to your own API, no third-party ESP account needed at all),
    # "brevo" (permanent free plan but requires a 1-2 day manual approval
    # ticket first), "sendgrid" (now a 60-day trial only, not permanent),
    # or "smtp" (local dev / paid Render plans - Render's free tier
    # blocks outbound SMTP ports entirely). Leave the matching
    # *_api_key/smtp_host empty to disable emails - notification calls
    # just no-op with a clear message.
    email_provider: str = "mailjet"

    # Used directly for EMAIL_PROVIDER=smtp, and also reused as the Gmail
    # credentials sent to your own relay for EMAIL_PROVIDER=custom (so you
    # only maintain one set of SMTP credentials, not two).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_email_to: str = ""  # falls back to the "email" field in the job-search config if empty

    # Custom relay (EMAIL_PROVIDER=custom) - your own self-hosted
    # send-email API (e.g. a C#/.NET endpoint on infra you control).
    # Bypasses every third-party ESP account-approval issue entirely,
    # since it's your own Gmail credentials sent to your own endpoint.
    custom_email_api_url: str = ""
    custom_email_api_key: str = ""  # optional - sent as "Authorization: Bearer <key>" if set

    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""  # must match your Single Sender Verified address
    sendgrid_from_name: str = ""

    # Brevo (https://www.brevo.com) - permanent free plan (300/day), but
    # gates transactional sending behind a manual support-ticket approval
    # for every new account (1-2 business day wait) - see README.
    brevo_api_key: str = ""
    brevo_from_email: str = ""  # must match your verified sender
    brevo_from_name: str = ""

    # Mailjet (https://www.mailjet.com) - permanent free plan (200/day,
    # 6000/month), no credit card. Unlike Brevo, transactional sending
    # works immediately after a normal sender-email confirmation click -
    # no manual review/support-ticket wait. Recommended if you don't
    # want to wait on Brevo's approval.
    mailjet_api_key: str = ""
    mailjet_api_secret: str = ""
    mailjet_from_email: str = ""  # must match your validated sender
    mailjet_from_name: str = ""

    # Scheduler
    enable_scheduler: bool = True
    daily_search_hour_utc: int = 3   # runs once a day at this UTC hour
    daily_reminder_hour_utc: int = 4


env_settings = EnvSettings()
