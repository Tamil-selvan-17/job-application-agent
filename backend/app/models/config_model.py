"""
This mirrors the JSON configuration the user uploads/edits from the UI.
It's intentionally permissive (all fields optional with sane defaults) so
partial updates from the UI never 500 out on a missing field.
"""
from pydantic import BaseModel, Field


class JobSearchConfig(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    experience: int = 0
    website_link: str = ""  # portfolio/personal site - included in HR application emails

    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)

    salary_min: int = 0
    salary_max: int = 0

    job_types: list[str] = Field(default_factory=lambda: ["Full Time"])
    remote: bool = True
    visa_required: bool = False

    experience_min: int = 0
    experience_max: int = 0

    company_blacklist: list[str] = Field(default_factory=list)
    company_whitelist: list[str] = Field(default_factory=list)

    keywords_include: list[str] = Field(default_factory=list)
    keywords_exclude: list[str] = Field(default_factory=list)

    followup_after_days: int = 5
    daily_job_limit: int = 50
    auto_apply: bool = False

    default_resume: str = ""
    default_cover_letter: str = ""

    language: str = "English"

    job_sources: list[str] = Field(
        default_factory=lambda: ["LinkedIn", "Indeed", "Naukri", "Wellfound"]
    )

    # Only keep jobs posted within this many days (server-side sources
    # like Adzuna also use this for their own recency search param).
    # Jobs with no parseable posting date are kept regardless (benefit
    # of the doubt) rather than penalized for missing data.
    job_posted_within_days: int = 45

    class Config:
        extra = "allow"  # forward-compatible: unknown keys won't be rejected
