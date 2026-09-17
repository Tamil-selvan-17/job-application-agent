"""
Enhanced Job Description Analyzer.

Extends the existing AI analysis (extracted_skills, match_percent, etc.) with
a richer STRUCTURED analysis used for resume customization and contact finding:

  jd_analysis = {
    "jobTitle": "",
    "company": "",
    "location": "",
    "experience": "",
    "employmentType": "",
    "requiredSkills": [],
    "preferredSkills": [],
    "responsibilities": [],
    "technologies": [],
    "keywords": [],
    "atsKeywords": [],
    "importantPhrases": [],
    "applicationUrl": "",
    "companyUrl": "",
    "recruiterSignals": [],
    "hooks": []   # 3-6 most important things to emphasize in the resume
  }

Stored in job document as `jd_analysis` field (separate from `analysis`).
Does NOT replace or break the existing `analyze_job()` in job_service.py.
"""
import json
import re
from datetime import datetime, timezone
from bson import ObjectId

from app.database.mongo import get_db
from app.services.ai_provider import get_ai_provider

JD_ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior technical recruiter and ATS optimization expert. "
    "You always respond with STRICT, VALID JSON ONLY — no markdown fences, "
    "no commentary, no text before or after the JSON object."
)

JD_ANALYSIS_PROMPT = """Analyze this job description deeply and return a single JSON object with EXACTLY these keys:

{{
  "jobTitle": "exact job title from the JD",
  "company": "company name",
  "location": "location string",
  "experience": "experience requirement e.g. '3-5 years'",
  "employmentType": "Full-time / Contract / Part-time",
  "requiredSkills": ["list of explicitly required technical skills"],
  "preferredSkills": ["list of nice-to-have or preferred skills"],
  "responsibilities": ["list of key responsibilities as stated in the JD"],
  "technologies": ["all technologies, frameworks, tools mentioned"],
  "keywords": ["important keywords that appear frequently in the JD"],
  "atsKeywords": ["exact ATS-optimized keywords a resume should contain to pass screening"],
  "importantPhrases": ["important exact phrases from the JD a resume should mirror"],
  "applicationUrl": "direct application URL if mentioned, else empty string",
  "companyUrl": "company website URL if mentioned, else empty string",
  "recruiterSignals": ["things the recruiter/company seems to value most based on tone and emphasis"],
  "hooks": ["3-6 most critical skills/experiences to emphasize in the resume to stand out for THIS specific role — these must be real skills the candidate can truthfully claim"]
}}

JOB DESCRIPTION:
---
{job_description}
---

Return ONLY the JSON object. No markdown. No explanation."""


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace:
            text = brace.group(1)
    return json.loads(text)


async def analyze_jd_structured(job_id: str) -> dict:
    """
    Runs a structured JD analysis and stores the result in job.jd_analysis.
    Returns the full updated job document.
    """
    db = get_db()
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise ValueError("Job not found")

    description = job.get("description", "")
    if not description.strip():
        raise ValueError("Job has no description to analyze")

    provider = await get_ai_provider()
    prompt = JD_ANALYSIS_PROMPT.format(job_description=description[:10000])
    raw = await provider.generate(prompt, system=JD_ANALYSIS_SYSTEM_PROMPT)

    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, AttributeError):
        parsed = {
            "jobTitle": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "experience": "",
            "employmentType": "",
            "requiredSkills": [],
            "preferredSkills": [],
            "responsibilities": [],
            "technologies": [],
            "keywords": [],
            "atsKeywords": [],
            "importantPhrases": [],
            "applicationUrl": job.get("url", ""),
            "companyUrl": "",
            "recruiterSignals": [],
            "hooks": [],
            "_parse_error": f"Could not parse AI response. Raw: {raw[:300]}",
        }

    parsed["analyzed_at"] = datetime.now(timezone.utc).isoformat()

    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {
            "$set": {
                "jd_analysis": parsed,
                "workflow_state": "JD_ANALYZED",
                "company_url": parsed.get("companyUrl", ""),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    updated = await db.jobs.find_one({"_id": ObjectId(job_id)})
    return _to_detail(updated)


def _to_detail(j: dict) -> dict:
    d = dict(j)
    d["id"] = str(d.pop("_id"))
    return d
