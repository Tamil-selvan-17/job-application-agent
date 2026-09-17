from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

JobStatus = Literal["new", "saved", "applied", "rejected", "interview", "offer", "not_responded"]

WorkflowState = Literal[
    "JOB_CREATED",
    "JD_ANALYZED",
    "RESUME_CUSTOMIZED",
    "DOCX_GENERATED",
    "PDF_GENERATED",
    "CONTACTS_FOUND",
    "EMAIL_READY",
    "EMAIL_SENT",
    "APPLICATION_STARTED",
    "APPLIED",
    "FAILED",
]

ResumeStatus = Literal["NOT_GENERATED", "GENERATING", "READY", "FAILED"]
EmailStatus = Literal["NOT_SENT", "SENT", "FAILED"]
ApplicationStatus = Literal["NOT_APPLIED", "APPLYING", "CAPTCHA_REQUIRED", "AWAITING_CONFIRMATION", "APPLIED", "FAILED"]


class JobCreate(BaseModel):
    title: str
    company: str
    description: str
    location: str = ""
    url: str = ""
    source: str = "manual"
    salary_text: str = ""
    hr_email: str = ""


class JobUpdate(BaseModel):
    title: str | None = None
    company: str | None = None
    description: str | None = None
    location: str | None = None
    url: str | None = None
    salary_text: str | None = None
    status: JobStatus | None = None
    notes: str | None = None
    application_method: str | None = None  # "website" | "email"
    hr_email: str | None = None


class JobAnalysis(BaseModel):
    provider: str = ""
    analyzed_at: datetime | None = None
    resume_id: str | None = None
    extracted_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    experience_required: str = ""
    salary_range: str = ""
    benefits: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    match_percent: int = 0
    match_reason: str = ""
    missing_skills: list[str] = Field(default_factory=list)
    learning_suggestions: list[str] = Field(default_factory=list)
    interview_difficulty: str = ""


class JobSummary(BaseModel):
    id: str
    title: str
    company: str
    location: str = ""
    source: str = "manual"
    status: JobStatus = "new"
    created_at: datetime
    updated_at: datetime
    match_percent: int | None = None


class ContactRecord(BaseModel):
    email: str
    source: str = ""
    confidence: int = 0          # 0-100
    contact_type: str = "OTHER"  # HR | RECRUITER | CAREERS | OTHER
    verified: bool = False
    name: str = ""


class JobDetail(JobSummary):
    url: str = ""
    salary_text: str = ""
    description: str = ""
    notes: str = ""
    analysis: JobAnalysis | None = None
    applied_at: datetime | None = None
    application_method: str | None = None  # "website" | "email"
    application_email_to: str | None = None
    hr_email: str | None = None          # authoritative - from Excel import or manual entry
    hr_email_guess: str | None = None    # fallback - auto-detected from the job description text
    # Multi-stage follow-up reminders: 1st (day 3), 2nd (day 5), 3rd (day 8),
    # then auto-marked "not_responded" at day 10 if still no reply.
    reminder_1_sent_at: datetime | None = None
    reminder_2_sent_at: datetime | None = None
    reminder_3_sent_at: datetime | None = None
    # --- New fields for full agent workflow ---
    workflow_state: WorkflowState = "JOB_CREATED"
    resume_status: ResumeStatus = "NOT_GENERATED"
    email_status: EmailStatus = "NOT_SENT"
    application_status: ApplicationStatus = "NOT_APPLIED"
    generated_resume_id: str | None = None   # ID in generated_resumes collection
    jd_analysis: dict | None = None          # Structured JD analysis (hooks, ATS keywords, etc.)
    contacts: list[ContactRecord] = Field(default_factory=list)  # Discovered HR contacts
    ats_score: int = 0                       # ATS score of generated resume vs this JD
    company_url: str = ""                    # Populated by JD analyzer if present in JD


class ExcelImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
