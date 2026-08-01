from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

JobStatus = Literal["new", "saved", "applied", "rejected", "interview", "offer"]


class JobCreate(BaseModel):
    title: str
    company: str
    description: str
    location: str = ""
    url: str = ""
    source: str = "manual"
    salary_text: str = ""


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


class JobDetail(JobSummary):
    url: str = ""
    salary_text: str = ""
    description: str = ""
    notes: str = ""
    analysis: JobAnalysis | None = None
    applied_at: datetime | None = None
    reminder_sent_at: datetime | None = None
    application_method: str | None = None  # "website" | "email"
    application_email_to: str | None = None
    hr_email_guess: str | None = None
