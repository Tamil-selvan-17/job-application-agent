"""
Candidate profile — the single source of truth for all personal data.

This is separate from JobSearchConfig (which controls job-search behaviour).
The CandidateProfile drives:
  - AI resume customization (what's true about the candidate)
  - Selenium form field mapping (what to fill in on application websites)
  - Personalized email body (which real skills to mention)

One profile document is stored in Mongo (candidate_profiles collection).
All existing config/job-search behaviour is unchanged.
"""
from typing import Literal
from pydantic import BaseModel, Field


class PersonalInfo(BaseModel):
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


class CareerInfo(BaseModel):
    current_title: str = ""
    total_experience: str = ""      # e.g. "4 years"
    notice_period: str = ""         # e.g. "30 days"
    expected_salary: str = ""       # e.g. "12-15 LPA"
    current_company: str = ""
    current_ctc: str = ""


class Education(BaseModel):
    degree: str = ""                # e.g. "B.E. Computer Science"
    institution: str = ""
    field_of_study: str = ""
    start_year: str = ""
    end_year: str = ""
    gpa: str = ""
    location: str = ""


class ExperienceEntry(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""            # e.g. "Jan 2022"
    end_date: str = ""              # e.g. "Present"
    current: bool = False
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str = ""
    description: str = ""
    role: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str = ""
    github_url: str = ""
    highlights: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    date: str = ""
    expiry: str = ""
    credential_id: str = ""
    url: str = ""


class WorkPreferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=lambda: ["Hybrid"])
    employment_type: list[str] = Field(default_factory=lambda: ["Full-time"])


class CandidateProfile(BaseModel):
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    career: CareerInfo = Field(default_factory=CareerInfo)
    skills: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    preferences: WorkPreferences = Field(default_factory=WorkPreferences)
    # ID of the original DOCX resume uploaded to the resumes collection.
    # This is the master template — it is NEVER modified.
    original_resume_id: str = ""
    # Free-text notes about the candidate not captured above
    additional_info: str = ""

    class Config:
        extra = "allow"
