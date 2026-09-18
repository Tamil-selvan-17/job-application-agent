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

    try:
        ai = get_ai_provider()
        raw_response = await ai.generate(prompt=user_prompt, system=system_prompt)
        data = _parse_json_response(raw_response, job_id, job_title, company, cand_skills)
    except Exception as e:
        logger.warning("[InterviewPrep] AI generation failed, using intelligent local fallback: %s", e)
        data = _parse_json_response("", job_id, job_title, company, cand_skills)

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


def _parse_json_response(text: str, job_id: str, job_title: str, company: str, cand_skills: list = None) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "questions" in parsed and len(parsed["questions"]) > 0:
            parsed["job_id"] = job_id
            return parsed
    except Exception as e:
        logger.warning("[InterviewPrep] Failed to parse AI JSON output: %s", e)

    skills_str = ", ".join(cand_skills[:3]) if cand_skills else "Core Software Engineering"

    return {
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "summary": f"Interview preparation guide for {job_title} at {company} focusing on {skills_str}.",
        "questions": [
            {
                "category": "Behavioral STAR",
                "question": f"Tell me about a complex project you led for {job_title} utilizing {skills_str}.",
                "why_asked": "Evaluating technical ownership, problem-solving abilities, and architectural decision making.",
                "star_answer": {
                    "situation": f"Architecting enterprise applications requiring high throughput and scalability.",
                    "task": "Deliver scalable API endpoints under tight performance SLAs and deadlines.",
                    "action": f"Designed modular services using {skills_str} and implemented automated integration testing.",
                    "result": "Successfully deployed to production with 99.9% uptime and 40% faster API response times."
                },
                "pro_tip": "Focus on quantifiable performance metrics and tech stack architectural choices."
            },
            {
                "category": "Technical Architecture",
                "question": f"How do you approach error handling, logging, and database transaction safety in enterprise services?",
                "why_asked": "Testing backend reliability, resilience patterns, and data consistency awareness.",
                "star_answer": {
                    "situation": "Handling concurrent database transactions across distributed application modules.",
                    "task": "Prevent deadlocks, race conditions, and ensure atomic rollbacks during API failures.",
                    "action": "Implemented retry loops, isolation levels, circuit breakers, and structured logging.",
                    "result": "Zero data inconsistency issues during peak load bursts."
                },
                "pro_tip": "Mention retry patterns, idempotent API design, and monitoring metrics."
            },
            {
                "category": "System Design & Optimization",
                "question": f"Walk me through how you optimize slow API response times or database queries under heavy load.",
                "why_asked": "Assessing performance tuning, database profiling, and debugging proficiency.",
                "star_answer": {
                    "situation": "API endpoints experiencing latency spikes under high concurrent user traffic.",
                    "task": "Reduce average response latency to under 200ms without increasing infrastructure cost.",
                    "action": "Analyzed query execution plans, added indexes, and implemented multi-level caching.",
                    "result": "Reduced average latency by 60% and improved throughput significantly."
                },
                "pro_tip": "Discuss profiling tools, indexing strategy, and caching layers."
            }
        ]
    }
