from datetime import datetime
from pydantic import BaseModel, Field


class ResumeSummary(BaseModel):
    id: str
    filename: str
    file_type: str
    is_default: bool
    current_version: int
    uploaded_at: datetime
    updated_at: datetime
    text_preview: str = ""


class ResumeDetail(ResumeSummary):
    extracted_text: str = ""


class ResumeVersion(BaseModel):
    id: str
    resume_id: str
    version: int
    filename: str
    created_at: datetime
    extracted_text: str = ""


class ResumeAnalysis(BaseModel):
    resume_id: str
    provider: str
    analyzed_at: datetime
    result_text: str
