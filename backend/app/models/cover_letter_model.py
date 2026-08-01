from datetime import datetime
from pydantic import BaseModel


class CoverLetterSummary(BaseModel):
    id: str
    filename: str
    file_type: str
    is_default: bool
    uploaded_at: datetime
    text_preview: str = ""


class CoverLetterDetail(CoverLetterSummary):
    extracted_text: str = ""
