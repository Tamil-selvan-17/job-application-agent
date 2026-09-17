"""
Agent Orchestrator Service.

Central workflow manager for the full job application pipeline.
Manages state transitions and coordinates all sub-services.

Workflow per job:
  JOB_CREATED → JD_ANALYZED → RESUME_CUSTOMIZED → DOCX_GENERATED →
  PDF_GENERATED → CONTACTS_FOUND → EMAIL_READY → [user action] →
  EMAIL_SENT / APPLICATION_STARTED → APPLIED

Key safety rules:
  - ATS score must be >= ATS_SCORE_THRESHOLD (90%) before storing resume.
  - Before generating a new resume, check if an existing one with ats_score >= 90 exists.
  - Deduplication: warn if this job has already been applied to.
  - Never auto-submit anything without explicit user confirmation.
"""
import asyncio
import logging
from datetime import datetime, timezone
from bson import ObjectId

from app.database.mongo import get_db
from app.services import (
    candidate_service,
    jd_analyzer_service,
    resume_customizer_service,
    docx_generator_service,
    pdf_generator_service,
    contact_finder_service,
    application_tracker_service,
    resume_service,
)
from app.services import email_service, config_service

logger = logging.getLogger(__name__)

ATS_SCORE_THRESHOLD = 90  # Minimum ATS match % to accept a generated resume


async def _get_job(job_id: str) -> dict:
    db = get_db()
    j = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not j:
        raise ValueError("Job not found")
    d = dict(j)
    d["id"] = str(d.pop("_id"))
    return d


async def _update_job(job_id: str, patch: dict) -> None:
    db = get_db()
    patch["updated_at"] = datetime.now(timezone.utc)
    await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": patch})


# --------------------------------------------------------------------------- #
#  Step 1 — Analyze JD (structured)                                           #
# --------------------------------------------------------------------------- #

async def run_jd_analysis(job_id: str) -> dict:
    """
    Runs structured JD analysis and updates the job document.
    Returns the updated job document with jd_analysis filled in.
    """
    logger.info("[Orchestrator] JD analysis started for job %s", job_id)
    result = await jd_analyzer_service.analyze_jd_structured(job_id)
    logger.info("[Orchestrator] JD analysis done for job %s", job_id)
    return result


# --------------------------------------------------------------------------- #
#  Step 2 — Find HR Contacts                                                  #
# --------------------------------------------------------------------------- #

async def run_contact_discovery(job_id: str) -> list[dict]:
    logger.info("[Orchestrator] Contact discovery started for job %s", job_id)
    contacts = await contact_finder_service.discover_and_store_contacts(job_id)
    logger.info("[Orchestrator] Found %d contacts for job %s", len(contacts), job_id)
    return contacts


# --------------------------------------------------------------------------- #
#  Step 3 — Customize Resume + Generate DOCX + PDF                            #
# --------------------------------------------------------------------------- #

async def run_resume_pipeline(job_id: str, force_regenerate: bool = False) -> dict:
    """
    Runs the full resume customization → DOCX → PDF pipeline.

    Before generating:
      1. Check for existing generated resume for this job.
      2. If ats_score >= ATS_SCORE_THRESHOLD, return existing (no regen needed).
      3. If force_regenerate or ats_score < threshold, regenerate.

    Returns a dict with: generated_resume_id, ats_score, docx_filename, pdf_filename.
    """
    job = await _get_job(job_id)

    # Check for existing resume
    if not force_regenerate:
        existing = await application_tracker_service.get_generated_resume_for_job(job_id)
        if existing and existing.get("ats_score", 0) >= ATS_SCORE_THRESHOLD:
            logger.info(
                "[Orchestrator] Existing resume for job %s has ATS score %d >= %d, reusing it.",
                job_id, existing["ats_score"], ATS_SCORE_THRESHOLD,
            )
            return {
                "generated_resume_id": existing["id"],
                "ats_score": existing["ats_score"],
                "docx_filename": existing["docx_filename"],
                "pdf_filename": existing["pdf_filename"],
                "reused_existing": True,
            }

    # Ensure JD analysis exists
    if not job.get("jd_analysis"):
        job = await run_jd_analysis(job_id)

    jd_analysis = job.get("jd_analysis", {})

    # Load candidate profile
    profile = await candidate_service.get_profile()
    if not profile:
        raise ValueError("Candidate profile not set up. Please fill in the Candidate Profile tab first.")

    # Load original DOCX resume
    original_resume_id = profile.get("original_resume_id", "")
    if not original_resume_id:
        raise ValueError("No original DOCX resume linked to your profile. Please upload your DOCX resume and mark it as your profile resume.")

    original_docx_bytes, original_filename = await resume_service.get_resume_file(original_resume_id)
    if not original_docx_bytes:
        raise ValueError("Original DOCX resume file content is missing. Please re-upload it.")

    original_resume_text = await _get_resume_text(original_resume_id)

    await _update_job(job_id, {"resume_status": "GENERATING"})

    # AI customization
    logger.info("[Orchestrator] Starting AI resume customization for job %s", job_id)
    customized = await resume_customizer_service.customize_resume(
        candidate_profile=profile,
        jd_analysis=jd_analysis,
        original_resume_text=original_resume_text,
    )

    ats_score = customized.get("ats_analysis", {}).get("match_percentage", 0)
    logger.info("[Orchestrator] ATS score for job %s: %d%%", job_id, ats_score)

    # Generate DOCX
    logger.info("[Orchestrator] Generating DOCX for job %s", job_id)
    docx_bytes = docx_generator_service.generate_resume_docx(
        original_docx_bytes=original_docx_bytes,
        customized_content=customized,
        candidate_profile=profile,
        job_title=job.get("title", ""),
        company=job.get("company", ""),
    )
    docx_filename = docx_generator_service.build_resume_filename(
        profile, job.get("company", ""), job.get("title", ""), "docx"
    )

    # Generate PDF (run sync docx2pdf in thread pool)
    logger.info("[Orchestrator] Converting DOCX to PDF for job %s", job_id)
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None, pdf_generator_service.convert_docx_to_pdf, docx_bytes
    )
    pdf_filename = docx_filename.replace(".docx", ".pdf")

    # Store in generated_resumes collection
    generated_resume_id = await application_tracker_service.store_generated_resume(
        job_id=job_id,
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        docx_bytes=docx_bytes,
        pdf_bytes=pdf_bytes,
        docx_filename=docx_filename,
        pdf_filename=pdf_filename,
        ats_score=ats_score,
        ats_analysis=customized.get("ats_analysis", {}),
        customization_summary=customized.get("customization_summary", []),
        hooks_used=customized.get("hooks_used", []),
    )

    # Update job status
    await _update_job(job_id, {
        "resume_status": "READY",
        "workflow_state": "PDF_GENERATED",
        "generated_resume_id": generated_resume_id,
        "ats_score": ats_score,
    })

    logger.info("[Orchestrator] Resume pipeline complete for job %s. ATS: %d%%", job_id, ats_score)
    return {
        "generated_resume_id": generated_resume_id,
        "ats_score": ats_score,
        "docx_filename": docx_filename,
        "pdf_filename": pdf_filename,
        "reused_existing": False,
        "customization_summary": customized.get("customization_summary", []),
        "hooks_used": customized.get("hooks_used", []),
        "ats_analysis": customized.get("ats_analysis", {}),
    }


async def _get_resume_text(resume_id: str) -> str:
    db = get_db()
    doc = await db.resumes.find_one({"_id": ObjectId(resume_id)})
    return doc.get("extracted_text", "") if doc else ""


# --------------------------------------------------------------------------- #
#  Step 4 — Email HR                                                          #
# --------------------------------------------------------------------------- #

async def run_email_application(
    job_id: str,
    hr_email: str,
    subject_override: str | None = None,
    html_override: str | None = None,
    generated_resume_id: str | None = None,
) -> dict:
    """
    Sends personalized application email with the generated PDF resume attached.
    Marks job status EMAIL_SENT on success.
    """
    job = await _get_job(job_id)

    # Deduplication check
    is_duplicate = await application_tracker_service.check_duplicate_application(job_id)
    if is_duplicate:
        return {
            "sent": False,
            "reason": "This job has already been applied to. Sending again would be a duplicate.",
            "duplicate": True,
        }

    # Get generated resume
    resume_id = generated_resume_id or job.get("generated_resume_id")
    if not resume_id:
        raise ValueError("No generated resume found. Please generate a resume first.")

    _, pdf_bytes, _, pdf_filename = await application_tracker_service.get_generated_resume_bytes(resume_id)
    if not pdf_bytes:
        raise ValueError("PDF resume content is missing. Please regenerate the resume.")

    config = await config_service.get_config()
    profile = await candidate_service.get_profile()
    jd_analysis = job.get("jd_analysis", {})

    # Build personalized email
    html = html_override or _build_personalized_email_html(job, config, profile, jd_analysis)
    personal = profile.get("personal", {})
    candidate_name = personal.get("full_name", "") or config.get("name", "Candidate")
    subject = subject_override or f"Application for {job.get('title', 'Open Position')} – {candidate_name}"

    result = await email_service.send_email(
        subject=subject,
        html_body=html,
        to=hr_email,
        attachments=[(pdf_bytes, pdf_filename)],
    )

    if result.get("sent"):
        from datetime import timezone
        now = datetime.now(timezone.utc)
        await _update_job(job_id, {
            "status": "applied",
            "applied_at": now,
            "application_method": "email",
            "application_email_to": hr_email,
            "email_status": "SENT",
            "workflow_state": "EMAIL_SENT",
        })
        # Mark resume as applied, schedule cleanup
        await application_tracker_service.mark_resume_applied(resume_id)
        # Create application record
        await application_tracker_service.create_application(
            job_id=job_id,
            company=job.get("company", ""),
            role=job.get("title", ""),
            application_url=hr_email,
            generated_resume_id=resume_id,
            ats_score=job.get("ats_score", 0),
            method="email",
        )

    return result


def _build_personalized_email_html(job: dict, config: dict, profile: dict, jd_analysis: dict) -> str:
    """Builds a personalized email body using real candidate data + JD context."""
    personal = profile.get("personal", {})
    career = profile.get("career", {})
    name = personal.get("full_name", "") or config.get("name", "Candidate")
    phone = personal.get("phone", "") or config.get("phone", "")
    email = personal.get("email", "") or config.get("email", "")
    linkedin = personal.get("linkedin", "")
    website = personal.get("website", "") or config.get("website_link", "")

    job_title = job.get("title", "this role")
    company = job.get("company", "your company")
    experience_years = career.get("total_experience", "") or str(config.get("experience", ""))

    hooks = [h for h in (jd_analysis.get("hooks") or []) if isinstance(h, str)]
    technologies = [t for t in (jd_analysis.get("technologies") or []) if isinstance(t, str)]
    candidate_skills = [s for s in (profile.get("skills") or config.get("skills") or []) if isinstance(s, str)]

    matching_skills = [s for s in candidate_skills if any(
        s.lower() in t.lower() or t.lower() in s.lower()
        for t in (hooks + technologies)
    )][:5]

    if not matching_skills:
        matching_skills = candidate_skills[:4]

    skills_phrase = ", ".join(matching_skills) if matching_skills else "relevant technologies"

    experience_list = profile.get("experience") or []
    project_ref = ""
    if isinstance(experience_list, list) and len(experience_list) > 0:
        recent = experience_list[0] if isinstance(experience_list[0], dict) else {}
        recent_techs = [t for t in (recent.get("technologies") or []) if isinstance(t, str)]
        matching_recent = [t for t in recent_techs if any(
            t.lower() in h.lower() or h.lower() in t.lower() for h in hooks
        )]
        if matching_recent and recent.get("company"):
            project_ref = f"In my most recent role at {recent.get('company')}, I worked with {', '.join(matching_recent[:3])}"

    website_line = f'<p>Portfolio: <a href="{website}">{website}</a></p>' if website else ""
    linkedin_line = f'<p>LinkedIn: <a href="{linkedin}">{linkedin}</a></p>' if linkedin else ""
    project_line = f"<p>{project_ref}.</p>" if project_ref else ""
    exp_clause = f"I have {experience_years} of experience" if experience_years else "I have experience"

    return f"""
<p>Dear Hiring Team,</p>
<p>
  I am writing to apply for the <b>{job_title}</b> position at <b>{company}</b>.
  {exp_clause} working with {skills_phrase}.
</p>
{project_line}
<p>I have attached my resume for your consideration and would welcome the opportunity to discuss
how my background aligns with the requirements of this role.</p>
{website_line}
{linkedin_line}
<p>
  Thank you for your time.<br><br>
  Best regards,<br>
  <b>{name}</b><br>
  {phone}<br>
  {email}
</p>
"""


# --------------------------------------------------------------------------- #
#  Step 5 — Website Application (Selenium)                                    #
# --------------------------------------------------------------------------- #

async def start_website_application(job_id: str, generated_resume_id: str | None = None) -> dict:
    """
    Starts the Selenium browser agent for this job.
    Returns immediately with initial status; frontend polls for updates.
    """
    from app.services import browser_agent_service

    job = await _get_job(job_id)
    url = job.get("url", "")
    if not url:
        raise ValueError("Job has no application URL.")

    # Deduplication check
    is_duplicate = await application_tracker_service.check_duplicate_application(job_id)
    if is_duplicate:
        return {
            "status": "DUPLICATE",
            "message": "This job has already been applied to.",
        }

    profile = await candidate_service.get_profile()
    resume_id = generated_resume_id or job.get("generated_resume_id")
    if not resume_id:
        raise ValueError("No generated resume found. Generate a resume first.")

    _, pdf_bytes, _, pdf_filename = await application_tracker_service.get_generated_resume_bytes(resume_id)

    # Resolve the actual application URL (follow redirects)
    from app.services.job_service import resolve_apply_url
    try:
        resolved_url = await resolve_apply_url(job_id)
    except Exception:
        resolved_url = url

    agent = browser_agent_service.BrowserAgent(job_id)
    await _update_job(job_id, {"application_status": "APPLYING", "workflow_state": "APPLICATION_STARTED"})

    # Run Selenium in thread pool (it's synchronous)
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(
        None,
        agent.start_application,
        resolved_url,
        profile,
        pdf_bytes,
    )

    return {
        "job_id": job_id,
        "status": state.status,
        "current_step": state.current_step,
        "fields_filled": state.fields_filled,
        "fields_skipped": state.fields_skipped,
        "form_preview": state.form_preview,
        "screenshot_b64": state.screenshot_b64,
        "error": state.error,
    }


async def confirm_website_application(job_id: str) -> dict:
    """Submit the application after user confirmation."""
    from app.services import browser_agent_service

    session = browser_agent_service.get_session(job_id)
    if not session:
        raise ValueError("No active browser session for this job. Please start the application again.")

    job = await _get_job(job_id)
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, session.submit_application)

    if state.status == "SUBMITTED":
        resume_id = job.get("generated_resume_id")
        await _update_job(job_id, {
            "status": "applied",
            "applied_at": datetime.now(timezone.utc),
            "application_method": "website",
            "application_status": "APPLIED",
            "workflow_state": "APPLIED",
        })
        if resume_id:
            await application_tracker_service.mark_resume_applied(resume_id)
        await application_tracker_service.create_application(
            job_id=job_id,
            company=job.get("company", ""),
            role=job.get("title", ""),
            application_url=job.get("url", ""),
            generated_resume_id=resume_id or "",
            ats_score=job.get("ats_score", 0),
            method="website",
        )
        browser_agent_service.close_session(job_id)

    return {
        "status": state.status,
        "current_step": state.current_step,
        "error": state.error,
        "screenshot_b64": state.screenshot_b64,
    }


async def cancel_website_application(job_id: str) -> dict:
    from app.services import browser_agent_service
    browser_agent_service.close_session(job_id)
    await _update_job(job_id, {"application_status": "NOT_APPLIED"})
    return {"status": "cancelled"}
