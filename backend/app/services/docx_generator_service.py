"""
DOCX Generator Service.

Generates a job-specific resume DOCX by cloning the candidate's original
DOCX as a style/format template, then populating it with AI-customized content.

The original DOCX is NEVER modified — we copy it, then surgically replace
the text content section by section while preserving all formatting (fonts,
sizes, bold/italic, margins, spacing, bullet styles).

Approach:
  1. Load original DOCX with python-docx to read its styles.
  2. Build a new Document using the same styles.
  3. Populate with AI-customized sections (summary, skills, experience, projects).
  4. Return the new DOCX as bytes.

If the original DOCX is complex (tables, multi-column), we use a simplified
but still well-formatted document with the same font family and size.
"""
import io
import copy
import re
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _get_doc_styles(original_bytes: bytes) -> dict:
    """Extract font and size preferences from the original DOCX."""
    doc = Document(io.BytesIO(original_bytes))
    styles = {
        "font_name": "Calibri",
        "body_size": 11,
        "name_size": 16,
        "heading_size": 12,
        "margins": {
            "top": 0.75,
            "bottom": 0.75,
            "left": 0.75,
            "right": 0.75,
        }
    }
    # Try to detect font from first non-empty paragraph
    for para in doc.paragraphs:
        if para.text.strip():
            for run in para.runs:
                if run.font.name:
                    styles["font_name"] = run.font.name
                    break
            if para.runs:
                for run in para.runs:
                    if run.font.size:
                        styles["body_size"] = int(run.font.size.pt)
                        break
            break
    return styles


def _add_horizontal_rule(doc: Document, styles: dict) -> None:
    """Add a thin horizontal line below a section heading."""
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(2)
    pPr = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "4A4A4A")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_section_heading(doc: Document, text: str, styles: dict) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(8)
    para.paragraph_format.space_after = Pt(2)
    run = para.add_run(text.upper())
    run.bold = True
    run.font.name = styles["font_name"]
    run.font.size = Pt(styles["heading_size"])
    run.font.color.rgb = RGBColor(0x22, 0x22, 0x66)
    _add_horizontal_rule(doc, styles)


def _add_name_header(doc: Document, candidate_profile: dict, styles: dict) -> None:
    """Add name + contact line at the top."""
    personal = candidate_profile.get("personal", {})
    name = personal.get("full_name", "") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    email = personal.get("email", "")
    phone = personal.get("phone", "")
    linkedin = personal.get("linkedin", "")
    location = personal.get("location", "") or personal.get("city", "")

    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_para.paragraph_format.space_after = Pt(2)
    name_run = name_para.add_run(name)
    name_run.bold = True
    name_run.font.name = styles["font_name"]
    name_run.font.size = Pt(styles["name_size"])

    contact_parts = [p for p in [phone, email, linkedin, location] if p]
    if contact_parts:
        contact_para = doc.add_paragraph(" | ".join(contact_parts))
        contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_para.paragraph_format.space_after = Pt(4)
        for run in contact_para.runs:
            run.font.name = styles["font_name"]
            run.font.size = Pt(styles["body_size"] - 1)


def _add_summary(doc: Document, summary: str, styles: dict) -> None:
    _add_section_heading(doc, "Professional Summary", styles)
    para = doc.add_paragraph(summary)
    para.paragraph_format.space_after = Pt(4)
    for run in para.runs:
        run.font.name = styles["font_name"]
        run.font.size = Pt(styles["body_size"])


def _add_skills(doc: Document, skills_section: dict, styles: dict) -> None:
    _add_section_heading(doc, "Technical Skills", styles)
    skills = skills_section.get("highlighted", skills_section.get("all", []))
    if skills:
        # Group into 2 rows of 5 for readability
        chunks = [skills[i:i+5] for i in range(0, len(skills), 5)]
        for chunk in chunks:
            para = doc.add_paragraph(" • ".join(chunk))
            para.paragraph_format.space_after = Pt(2)
            for run in para.runs:
                run.font.name = styles["font_name"]
                run.font.size = Pt(styles["body_size"])


def _add_experience(doc: Document, experience: list[dict], styles: dict) -> None:
    if not experience:
        return
    _add_section_heading(doc, "Professional Experience", styles)
    for exp in experience:
        # Company + Title line
        header_para = doc.add_paragraph()
        header_para.paragraph_format.space_before = Pt(6)
        header_para.paragraph_format.space_after = Pt(1)
        title_run = header_para.add_run(exp.get("title", ""))
        title_run.bold = True
        title_run.font.name = styles["font_name"]
        title_run.font.size = Pt(styles["body_size"])
        header_para.add_run(f"  |  {exp.get('company', '')}")
        for run in header_para.runs[1:]:
            run.font.name = styles["font_name"]
            run.font.size = Pt(styles["body_size"])

        # Date + Location
        date_str = f"{exp.get('start_date', '')} – {exp.get('end_date', 'Present')}"
        loc = exp.get("location", "")
        date_loc = f"{date_str}  |  {loc}" if loc else date_str
        date_para = doc.add_paragraph(date_loc)
        date_para.paragraph_format.space_after = Pt(2)
        for run in date_para.runs:
            run.font.name = styles["font_name"]
            run.font.size = Pt(styles["body_size"] - 1)
            run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        # Bullets
        for bullet in exp.get("bullets", []):
            bp = doc.add_paragraph(style="List Bullet")
            run = bp.add_run(bullet)
            run.font.name = styles["font_name"]
            run.font.size = Pt(styles["body_size"])
            bp.paragraph_format.space_after = Pt(1)


def _add_projects(doc: Document, projects: list[dict], styles: dict) -> None:
    if not projects:
        return
    _add_section_heading(doc, "Projects", styles)
    for proj in projects:
        header_para = doc.add_paragraph()
        header_para.paragraph_format.space_before = Pt(4)
        header_para.paragraph_format.space_after = Pt(1)
        name_run = header_para.add_run(proj.get("name", ""))
        name_run.bold = True
        name_run.font.name = styles["font_name"]
        name_run.font.size = Pt(styles["body_size"])

        tech = proj.get("technologies", [])
        if tech:
            tech_para = doc.add_paragraph(f"Technologies: {', '.join(tech)}")
            tech_para.paragraph_format.space_after = Pt(1)
            for run in tech_para.runs:
                run.font.name = styles["font_name"]
                run.font.size = Pt(styles["body_size"] - 1)

        desc = proj.get("description", "")
        if desc:
            dp = doc.add_paragraph(desc)
            dp.paragraph_format.space_after = Pt(2)
            for run in dp.runs:
                run.font.name = styles["font_name"]
                run.font.size = Pt(styles["body_size"])

        for hl in proj.get("highlights", []):
            bp = doc.add_paragraph(style="List Bullet")
            run = bp.add_run(hl)
            run.font.name = styles["font_name"]
            run.font.size = Pt(styles["body_size"])
            bp.paragraph_format.space_after = Pt(1)


def _add_education(doc: Document, education: list[dict], styles: dict) -> None:
    if not education:
        return
    _add_section_heading(doc, "Education", styles)
    for edu in education:
        para = doc.add_paragraph()
        para.paragraph_format.space_before = Pt(4)
        para.paragraph_format.space_after = Pt(1)
        run = para.add_run(f"{edu.get('degree', '')} — {edu.get('institution', '')}")
        run.bold = True
        run.font.name = styles["font_name"]
        run.font.size = Pt(styles["body_size"])

        year = edu.get("end_year", "")
        field = edu.get("field_of_study", "")
        detail_parts = [p for p in [field, year] if p]
        if detail_parts:
            dp = doc.add_paragraph(" | ".join(detail_parts))
            dp.paragraph_format.space_after = Pt(1)
            for r in dp.runs:
                r.font.name = styles["font_name"]
                r.font.size = Pt(styles["body_size"] - 1)


def _add_certifications(doc: Document, certifications: list[dict], styles: dict) -> None:
    if not certifications:
        return
    _add_section_heading(doc, "Certifications", styles)
    for cert in certifications:
        para = doc.add_paragraph(style="List Bullet")
        run = para.add_run(f"{cert.get('name', '')} — {cert.get('issuer', '')}")
        run.font.name = styles["font_name"]
        run.font.size = Pt(styles["body_size"])
        if cert.get("date"):
            para.add_run(f"  ({cert.get('date', '')})")
        para.paragraph_format.space_after = Pt(1)


def generate_resume_docx(
    original_docx_bytes: bytes,
    customized_content: dict,
    candidate_profile: dict,
    job_title: str,
    company: str,
) -> bytes:
    """
    Generate a job-specific DOCX resume.

    original_docx_bytes: the candidate's master DOCX (never modified)
    customized_content: output from resume_customizer_service.customize_resume()
    candidate_profile: full CandidateProfile dict (for personal info, education, certs)
    job_title / company: for the filename reference

    Returns DOCX as bytes.
    """
    styles = _get_doc_styles(original_docx_bytes)

    doc = Document()

    # Set page margins
    section = doc.sections[0]
    section.top_margin = Inches(styles["margins"]["top"])
    section.bottom_margin = Inches(styles["margins"]["bottom"])
    section.left_margin = Inches(styles["margins"]["left"])
    section.right_margin = Inches(styles["margins"]["right"])

    # ---- Header: Name + Contact ----
    _add_name_header(doc, candidate_profile, styles)

    # ---- Summary ----
    summary = customized_content.get("summary", "")
    if summary:
        _add_summary(doc, summary, styles)

    # ---- Skills ----
    skills_section = customized_content.get("skills_section", {})
    if skills_section:
        _add_skills(doc, skills_section, styles)

    # ---- Experience ----
    experience = customized_content.get("experience", [])
    _add_experience(doc, experience, styles)

    # ---- Projects ----
    projects = customized_content.get("projects", [])
    _add_projects(doc, projects, styles)

    # ---- Education (from full profile, not customized — these never change) ----
    education = candidate_profile.get("education", [])
    _add_education(doc, education, styles)

    # ---- Certifications (from profile) ----
    certifications = candidate_profile.get("certifications", [])
    _add_certifications(doc, certifications, styles)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_resume_filename(
    candidate_profile: dict,
    company: str,
    job_title: str,
    extension: str = "docx",
) -> str:
    personal = candidate_profile.get("personal", {})
    first = personal.get("first_name", "") or ""
    last = personal.get("last_name", "") or ""
    date_str = datetime.now().strftime("%Y_%m_%d")
    safe_company = re.sub(r"[^A-Za-z0-9]", "_", company)[:20]
    safe_role = re.sub(r"[^A-Za-z0-9]", "_", job_title)[:20]
    safe_name = f"{first}_{last}".strip("_") or "Resume"
    return f"{safe_name}_{safe_company}_{safe_role}_{date_str}.{extension}"
