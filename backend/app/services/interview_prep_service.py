"""
Interview Preparation Agent Service.

Generates hyper-personalized interview Q&As tailored to specific job descriptions
and candidate experience using the STAR (Situation-Task-Action-Result) method.
"""
import json
import logging
import re
from datetime import datetime, timezone
from bson import ObjectId

from app.database.mongo import get_db
from app.services import candidate_service, job_service
from app.services.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


async def generate_interview_prep(job_id: str, force: bool = False) -> dict:
    """
    Generates 8-10 interview questions with detailed STAR answers tailored
    to the job requirements and candidate profile.
    """
    db = get_db()
    existing = await db.interview_preps.find_one({"job_id": job_id})
    if existing and not force:
        d = dict(existing)
        d["id"] = str(d.pop("_id"))
        return d

    job = await job_service.get_job(job_id)
    profile = await candidate_service.get_profile()

    job_title = job.get("title", "Software Engineer")
    company = job.get("company", "Company")
    description = job.get("description", "") or job.get("raw_description", "")
    skills_req = job.get("jd_analysis", {}).get("required_skills", []) or job.get("tags", [])

    personal = profile.get("personal", {})
    candidate_name = personal.get("full_name", "Candidate")
    cand_skills = profile.get("skills", [])
    cand_exp = profile.get("experience", [])
    cand_projects = profile.get("projects", [])

    system_prompt = (
        "You are an expert Executive Interview Coach and Senior Technical Recruiter. "
        "Your goal is to prepare candidates for high-stakes interviews with tailored STAR method answers. "
        "Return ONLY a valid JSON object without markdown formatting."
    )

    user_prompt = f"""
Candidate Name: {candidate_name}
Candidate Skills: {', '.join(cand_skills)}
Candidate Projects: {json.dumps(cand_projects, indent=2)}
Candidate Experience Summary: {json.dumps(cand_exp, indent=2)}

Target Company: {company}
Target Role: {job_title}
Key Job Requirements: {', '.join(skills_req)}
Job Description Excerpt:
{description[:1500]}

Generate 8 detailed interview questions specifically relevant to this candidate applying for this role at {company}.
Include a mix of Technical, System Design, Behavioral (STAR method), and Role Fit questions.

Return JSON in this EXACT format:
{{
  "job_id": "{job_id}",
  "job_title": "{job_title}",
  "company": "{company}",
  "summary": "Brief 2-sentence coaching overview for this interview.",
  "questions": [
    {{
      "category": "Behavioral STAR / Technical / System Design / Role Fit",
      "question": "The interview question text",
      "why_asked": "Explanation of what the interviewer is testing",
      "star_answer": {{
        "situation": "Context from candidate background or typical scenario",
        "task": "Specific challenge or objective to solve",
        "action": "Concrete steps taken using technologies like {', '.join(cand_skills[:5])}",
        "result": "Quantifiable positive business or technical outcome"
      }},
      "pro_tip": "Key strategy or phrase to stand out"
    }}
  ]
}}
"""

    ai = get_ai_provider()
    raw_response = await ai.generate(prompt=user_prompt, system=system_prompt)

    data = _parse_json_response(raw_response, job_id, job_title, company)
    now = datetime.now(timezone.utc)
    data["created_at"] = now
    data["updated_at"] = now

    await db.interview_preps.delete_many({"job_id": job_id})
    result = await db.interview_preps.insert_one(data)
    data["id"] = str(result.inserted_id)
    if "_id" in data:
        data.pop("_id")
    return data


async def get_interview_prep(job_id: str) -> dict | None:
    db = get_db()
    existing = await db.interview_preps.find_one({"job_id": job_id})
    if not existing:
        return None
    d = dict(existing)
    d["id"] = str(d.pop("_id"))
    return d


def _parse_json_response(text: str, job_id: str, job_title: str, company: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "questions" in parsed:
            parsed["job_id"] = job_id
            return parsed
    except Exception as e:
        logger.warning("[InterviewPrep] Failed to parse AI JSON output: %s", e)

    return {
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "summary": f"Interview prep package for {job_title} at {company}.",
        "questions": [
            {
                "category": "Behavioral STAR",
                "question": f"Tell me about a complex project you led relevant to {job_title}.",
                "why_asked": "Testing problem solving and ownership.",
                "star_answer": {
                    "situation": "Working on core architecture.",
                    "task": "Deliver scalable backend service under tight deadline.",
                    "action": "Applied best practices and optimized execution.",
                    "result": "Successfully deployed with high reliability."
                },
                "pro_tip": "Highlight quantifiable metrics and tech stack decisions."
            }
        ]
    }
