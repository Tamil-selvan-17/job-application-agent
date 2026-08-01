"""
Shared keyword matching used by job search relevance filtering and
exclude-keyword filtering.

Plain substring matching is unsafe for short/generic keywords - e.g. the
skill "Git" is a substring of the very common word "digital"
(di-GIT-al), so a naive `"git" in text` check quietly let irrelevant
jobs through. This uses word-boundary regex for alphanumeric terms so
"Git" only matches the standalone word "Git", not a chunk of another
word - while still handling terms with punctuation (".NET Core", "C#",
"REST API") sensibly via a plain (but still case-insensitive) match.
"""
import re
from datetime import datetime, timezone
from langdetect import detect, LangDetectException

_LANGUAGE_NAME_TO_CODE = {
    "english": "en",
    "german": "de",
    "french": "fr",
    "spanish": "es",
    "portuguese": "pt",
    "hindi": "hi",
    "tamil": "ta",
    "any": None,
}


def _compile_term(term: str) -> re.Pattern | None:
    term = (term or "").strip()
    if not term:
        return None
    # Only use strict \b word-boundary matching for terms made purely of
    # letters/digits/spaces (e.g. "Git", "Angular", "SQL Server"). Terms with
    # leading/trailing punctuation ("C#", ".NET Core", "REST-API") break \b
    # in unintuitive ways (a boundary can't form between two non-word chars,
    # e.g. a space followed by "."), so those fall back to a plain
    # case-insensitive substring match instead.
    if re.fullmatch(r"[A-Za-z0-9 ]+", term):
        pattern = r"\b" + re.escape(term) + r"\b"
    else:
        pattern = re.escape(term)
    return re.compile(pattern, re.IGNORECASE)


def keyword_hits(text: str, terms: list[str]) -> list[str]:
    """Returns the subset of `terms` that actually appear in `text` as whole words/phrases."""
    text = text or ""
    hits = []
    for term in terms:
        pattern = _compile_term(term)
        if pattern and pattern.search(text):
            hits.append(term)
    return hits


def any_keyword_matches(text: str, terms: list[str]) -> bool:
    return len(keyword_hits(text, terms)) > 0


import re as _re

_EMAIL_PATTERN = _re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def extract_email(text: str) -> str | None:
    """Best-effort: finds the first email address mentioned in job text, if any."""
    match = _EMAIL_PATTERN.search(text or "")
    return match.group(0) if match else None


def matches_language(text: str, target_language: str | None) -> bool:
    """
    Returns True if `text` appears to be written in `target_language`
    (e.g. "English"). Unrecognized/empty target languages, or text too
    short for reliable detection, default to True (keep the job) rather
    than silently dropping it - detection errors shouldn't cost you a
    real match.
    """
    if not target_language:
        return True
    target_code = _LANGUAGE_NAME_TO_CODE.get(target_language.strip().lower(), "en")
    if target_code is None:  # "Any"
        return True

    sample = (text or "").strip()
    if len(sample) < 40:  # too short to detect reliably - don't penalize it
        return True

    try:
        detected = detect(sample[:2000])
    except LangDetectException:
        return True

    return detected == target_code


def matches_location(job_location: str, preferred_locations: list[str], remote_ok: bool) -> bool:
    """
    A job passes if: no location preference is set at all, OR it's
    remote and remote is acceptable, OR its location text mentions one
    of the preferred locations. This is deliberately permissive (keeps
    a job if in doubt) rather than aggressively excluding on ambiguous
    location text.
    """
    job_location = (job_location or "").strip()
    if not preferred_locations:
        return True
    if remote_ok and "remote" in job_location.lower():
        return True
    if not job_location:
        return True  # unknown location - don't penalize, let keyword/other filters decide
    lowered = job_location.lower()
    return any(loc.lower() in lowered for loc in preferred_locations if loc.strip())


def matches_job_type(job_type_text: str, preferred_job_types: list[str]) -> bool:
    """Soft match - if the source didn't report a job type, don't filter on it."""
    job_type_text = (job_type_text or "").strip()
    if not preferred_job_types or not job_type_text:
        return True
    normalize = lambda s: re.sub(r"[\s_-]+", "", s).lower()
    job_norm = normalize(job_type_text)
    return any(normalize(t) in job_norm or job_norm in normalize(t) for t in preferred_job_types)


_EXPERIENCE_PATTERN = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to)?\s*(\d{1,2})?\s*year", re.IGNORECASE)


def extract_min_experience_years(text: str) -> int | None:
    """Best-effort regex extraction of the minimum years of experience mentioned in a JD."""
    match = _EXPERIENCE_PATTERN.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def matches_experience(text: str, experience_max: int | None, buffer_years: int = 3) -> bool:
    """
    Rejects only when the JD clearly asks for meaningfully more
    experience than the candidate's stated max (with a buffer, since
    "5+ years" postings routinely consider 4-year candidates). Doesn't
    reject on unclear/missing experience text - regex extraction from
    free text is noisy, so this only filters the clear-cut over-senior
    case rather than risking false negatives on ambiguous wording.
    """
    if not experience_max:
        return True
    required = extract_min_experience_years(text)
    if required is None:
        return True
    return required <= experience_max + buffer_years


def is_recent_enough(posted_at: str | None, max_age_days: int = 45) -> bool:
    """Keeps jobs with no parseable date (benefit of the doubt) or within max_age_days."""
    if not posted_at:
        return True
    try:
        posted = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - posted).days
    return age_days <= max_age_days
