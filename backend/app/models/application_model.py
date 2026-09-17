"""
Application tracking model.

Tracks every job application submitted — either via email or website.
Stored in the `applications` Mongo collection.
Separate from the job document so a single job can have multiple
application records (email + website, retries, etc.) without polluting
the job document.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "PENDING",
    "EMAIL_SENT",
    "WEBSITE_APPLYING",
    "APPLIED",
    "FAILED",
    "CAPTCHA_REQUIRED",
    "AWAITING_CONFIRMATION",
]

ApplicationMethod = Literal["email", "website", "both"]


class ApplicationRecord(BaseModel):
    id: str = ""
    job_id: str
    company: str
    role: str
    application_url: str = ""
    generated_resume_id: str = ""   # ID in generated_resumes collection
    ats_score: int = 0
    method: ApplicationMethod = "email"
    email_sent: bool = False
    email_sent_at: datetime | None = None
    email_to: str = ""
    website_applied: bool = False
    applied_at: datetime | None = None
    status: ApplicationStatus = "PENDING"
    error: str | None = None
    screenshot_path: str | None = None  # Failure screenshot (relative path in uploads/)
    failed_step: str | None = None      # Which step failed, e.g. "PHONE_NUMBER"
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())


class GeneratedResumeRecord(BaseModel):
    """
    Represents a job-specific customized resume (DOCX + PDF).
    Stored in the generated_resumes Mongo collection.
    Files stored as base64 (same pattern as regular resumes).
    Scheduled for deletion 1 day after the application is marked APPLIED.
    """
    id: str
    job_id: str
    job_title: str
    company: str
    docx_filename: str
    pdf_filename: str
    ats_score: int = 0
    ats_analysis: dict = Field(default_factory=dict)
    customization_summary: list[str] = Field(default_factory=list)  # What was changed
    hooks_used: list[str] = Field(default_factory=list)             # JD hooks woven in
    created_at: datetime
    applied_at: datetime | None = None
    scheduled_delete_at: datetime | None = None  # Set to applied_at + 1 day on application
