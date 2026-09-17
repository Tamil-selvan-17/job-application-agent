"""
DOCX Generator Service.

Generates a job-specific resume DOCX by cloning the candidate's original
DOCX as a style/format template, then populating it with AI-customized content.

The original DOCX is NEVER modified — we copy it, then surgically replace
the text content section by section while preserving all formatting (fonts,
sizes, bold/italic, margins, spacing, bullet styles, colors, and active hyperlinks).
"""
import io
import re
import logging
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement, parse_xml

logger = logging.getLogger(__name__)


def add_hyperlink(paragraph, url: str, text: str, color_hex: str = "1d4ed8", underline: bool = True, font_name: str = None, font_size: float = None):
    """
    Adds a real, clickable Word hyperlink (<w:hyperlink>) to a python-docx paragraph.
    """
    if not url:
        r = paragraph.add_run(text)
        if font_name: r.font.name = font_name
        if font_size: r.font.size = Pt(font_size)
        return

    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    if color_hex:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), color_hex)
        rPr.append(c)

    if underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)

    if font_name:
        f = OxmlElement("w:rFonts")
        f.set(qn("w:ascii"), font_name)
        f.set(qn("w:hAnsi"), font_name)
        rPr.append(f)

    if font_size:
        sz_val = str(int(font_size * 2))
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), sz_val)
        rPr.append(sz)

    new_run.append(rPr)
    text_xml = OxmlElement("w:t")
    text_xml.text = text
    new_run.append(text_xml)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _get_doc_styles(original_bytes: bytes) -> dict:
    """Extract font and size preferences from the original DOCX."""
    styles = {
        "font_name": "Calibri",
        "body_size": 10.5,
        "name_size": 22,
        "heading_size": 11,
        "margins": {"top": 0.6, "bottom": 0.6, "left": 0.6, "right": 0.6}
    }
    if not original_bytes:
        return styles

    try:
        doc = Document(io.BytesIO(original_bytes))
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
    except Exception:
        pass
    return styles


def _add_section_heading(doc: Document, text: str, styles: dict) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(10)
    para.paragraph_format.space_after = Pt(3)
    run = para.add_run(text.upper())
    run.bold = True
    run.font.name = styles.get("font_name", "Calibri")
    run.font.size = Pt(styles.get("heading_size", 11))
    run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Add solid full-width bottom border
    pPr = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")  # 1pt thickness
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), "0F172A")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_name_header(doc: Document, candidate_profile: dict, styles: dict) -> None:
    """Add title + subtitle + active clickable contact hyperlinks."""
    personal = candidate_profile.get("personal", {})
    name = personal.get("full_name", "") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "TAMILSELVAN G"
    phone = personal.get("phone", "") or "+91 7200206323"
    email = personal.get("email", "") or "tamilselvang0002@gmail.com"
    location = personal.get("location", "") or personal.get("city", "") or "Chennai, India"
    linkedin = personal.get("linkedin", "") or "https://linkedin.com"
    github = personal.get("github", "") or "https://github.com"
    portfolio = personal.get("portfolio_url", "") or personal.get("website", "") or "https://portfolio.dev"

    font_name = styles.get("font_name", "Calibri")

    # Name Title Line
    name_para = doc.add_paragraph()
    name_para.paragraph_format.space_after = Pt(1)
    name_run = name_para.add_run(name.upper())
    name_run.bold = True
    name_run.font.name = font_name
    name_run.font.size = Pt(22)
    name_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Subtitle Line (Roles / Tech)
    target_role = candidate_profile.get("target_role", "") or candidate_profile.get("career", {}).get("current_title", "") or "Full Stack Software Engineer"
    subtitle_text = f"{target_role} | Angular | .NET Core | AI / RAG | SQL Server | Redis | AWS"
    sub_para = doc.add_paragraph()
    sub_para.paragraph_format.space_after = Pt(3)
    sub_run = sub_para.add_run(subtitle_text)
    sub_run.bold = True
    sub_run.font.name = font_name
    sub_run.font.size = Pt(10.5)
    sub_run.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)

    # Contact Line with Clickable Word Hyperlinks
    contact_para = doc.add_paragraph()
    contact_para.paragraph_format.space_after = Pt(6)

    # Phone
    r_phone = contact_para.add_run(f"{phone} | ")
    r_phone.font.name = font_name; r_phone.font.size = Pt(9.5)

    # Email
    add_hyperlink(contact_para, f"mailto:{email}", email, color_hex="1d4ed8", underline=True, font_name=font_name, font_size=9.5)
    r_sep1 = contact_para.add_run(" | ")
    r_sep1.font.name = font_name; r_sep1.font.size = Pt(9.5)

    # Location
    r_loc = contact_para.add_run(f"{location} | ")
    r_loc.font.name = font_name; r_loc.font.size = Pt(9.5)

    # LinkedIn Link
    add_hyperlink(contact_para, linkedin if linkedin.startswith("http") else f"https://{linkedin}", "LinkedIn", color_hex="1d4ed8", underline=True, font_name=font_name, font_size=9.5)
    r_sep2 = contact_para.add_run(" | ")
    r_sep2.font.name = font_name; r_sep2.font.size = Pt(9.5)

    # GitHub Link
    add_hyperlink(contact_para, github if github.startswith("http") else f"https://{github}", "GitHub", color_hex="1d4ed8", underline=True, font_name=font_name, font_size=9.5)
    r_sep3 = contact_para.add_run(" | ")
    r_sep3.font.name = font_name; r_sep3.font.size = Pt(9.5)

    # Portfolio Link
    add_hyperlink(contact_para, portfolio if portfolio.startswith("http") else f"https://{portfolio}", "Portfolio", color_hex="1d4ed8", underline=True, font_name=font_name, font_size=9.5)


def _add_summary(doc: Document, summary: str, styles: dict) -> None:
    _add_section_heading(doc, "Professional Summary", styles)
    para = doc.add_paragraph(summary)
    para.paragraph_format.space_after = Pt(4)
    para.paragraph_format.line_spacing = 1.15
    for run in para.runs:
        run.font.name = styles.get("font_name", "Calibri")
        run.font.size = Pt(styles.get("body_size", 10.5))
        run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)


def _add_skills(doc: Document, skills_section: dict, candidate_profile: dict, styles: dict) -> None:
    _add_section_heading(doc, "Technical Skills", styles)
    font_name = styles.get("font_name", "Calibri")
    body_size = styles.get("body_size", 10)

    categories = [
        ("Frontend", ["Angular 14–20", "TypeScript", "JavaScript (ES6+)", "RxJS", "HTML5", "CSS3", "Tailwind CSS", "Bootstrap", "Lazy Loading", "ApexCharts", "TinyMCE", "Angular Material", "Responsive UI Development", "State Management", "Reactive Forms"]),
        ("Backend", ["ASP.NET Core", "C#", "Web API", "RESTful Services", "SignalR", "JWT Authentication", "Entity Framework Core", "Clean Architecture", "SOLID Principles", "Middleware", "Dependency Injection", "Exception Handling"]),
        ("Database", ["SQL Server", "Query Optimization", "Indexing", "Stored Procedures", "MongoDB (Basic)", "Database Design", "Performance Optimization"]),
        ("Testing & Debugging", ["Manual Testing", "API Testing", "Unit Testing", "Debugging", "Bug Fixing", "Postman", "Swagger/OpenAPI", "Chrome DevTools"]),
        ("Cache & Infra", ["Redis (Caching, Session, Pub/Sub)", "Docker", "Docker Compose", "AWS S3", "CI/CD", "GitHub Actions"]),
        ("AI & Tools", ["Retrieval-Augmented Generation (RAG)", "LLM Integration (API Key, Ollama)", "Vector Embeddings", "SSE Streaming", "Prompt Engineering", "Postman", "Swagger/OpenAPI", "Git", "Agile/Scrum"]),
    ]

    custom_highlighted = set(s.lower() for s in skills_section.get("highlighted", []))

    for cat_name, cat_skills in categories:
        para = doc.add_paragraph()
        para.paragraph_format.space_before = Pt(1)
        para.paragraph_format.space_after = Pt(2)

        r_cat = para.add_run(f"{cat_name}: ")
        r_cat.bold = True
        r_cat.font.name = font_name
        r_cat.font.size = Pt(body_size)
        r_cat.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

        # Reorder to put JD-relevant skills first
        sorted_skills = sorted(cat_skills, key=lambda x: 0 if any(h in x.lower() for h in custom_highlighted) else 1)
        r_val = para.add_run(", ".join(sorted_skills))
        r_val.font.name = font_name
        r_val.font.size = Pt(body_size)
        r_val.font.color.rgb = RGBColor(0x33, 0x41, 0x55)


def _add_experience(doc: Document, experience: list[dict], candidate_profile: dict, styles: dict) -> None:
    if not experience:
        return
    _add_section_heading(doc, "Professional Experience", styles)
    font_name = styles.get("font_name", "Calibri")
    body_size = styles.get("body_size", 10)

    for exp in experience:
        para = doc.add_paragraph()
        para.paragraph_format.space_before = Pt(6)
        para.paragraph_format.space_after = Pt(1)

        title = exp.get("title", "") or exp.get("role", "")
        company = exp.get("company", "")
        location = exp.get("location", "")
        start_date = exp.get("start_date", "")
        end_date = exp.get("end_date", "Present")
        date_str = f"{start_date} – {end_date}" if start_date else end_date

        header_text = f"{title} — {company}"
        if location:
            header_text += f", {location}"

        r_head = para.add_run(header_text)
        r_head.bold = True
        r_head.font.name = font_name
        r_head.font.size = Pt(body_size + 0.5)
        r_head.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

        r_date = para.add_run(f"\t{date_str}")
        r_date.bold = True
        r_date.font.name = font_name
        r_date.font.size = Pt(body_size)
        r_date.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

        progression = exp.get("progression") or "Progression: Trainee → Junior → Associate Software Engineer"
        if progression:
            prog_para = doc.add_paragraph()
            prog_para.paragraph_format.space_after = Pt(2)
            r_prog = prog_para.add_run(progression)
            r_prog.italic = True
            r_prog.font.name = font_name
            r_prog.font.size = Pt(9)
            r_prog.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

        for b in exp.get("bullets", []):
            bp = doc.add_paragraph(style="List Bullet")
            bp.paragraph_format.space_after = Pt(2)
            r_b = bp.add_run(b)
            r_b.font.name = font_name
            r_b.font.size = Pt(body_size)
            r_b.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)


def _update_doc_in_place(doc: Document, customized_content: dict, candidate_profile: dict, styles: dict) -> bool:
    """
    Performs text replacements directly inside the cloned master DOCX.
    Preserves all paragraph formats, run fonts, colors, bullet styles, margins, and headers.
    """
    summary = customized_content.get("summary", "")
    skills_section = customized_content.get("skills_section", {})
    experience = customized_content.get("experience", [])

    section_paragraphs = {}
    current_section = None

    heading_patterns = {
        "summary": re.compile(r"summary|profile|objective|about", re.I),
        "skills": re.compile(r"skill|competenc|technolog|expertise", re.I),
        "experience": re.compile(r"experience|employment|work history|career", re.I),
        "projects": re.compile(r"project", re.I),
    }

    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue
        matched_sec = None
        for sec_key, pattern in heading_patterns.items():
            if pattern.search(txt) and len(txt) < 45:
                matched_sec = sec_key
                break
        if matched_sec:
            current_section = matched_sec
            if current_section not in section_paragraphs:
                section_paragraphs[current_section] = []
        elif current_section:
            section_paragraphs[current_section].append(para)

    if not section_paragraphs:
        return False

    # 1. Update Summary in-place preserving runs
    if summary and "summary" in section_paragraphs and section_paragraphs["summary"]:
        summary_paras = section_paragraphs["summary"]
        if summary_paras[0].runs:
            summary_paras[0].runs[0].text = summary
            for r in summary_paras[0].runs[1:]:
                r.text = ""
        else:
            summary_paras[0].text = summary
        for extra_p in summary_paras[1:]:
            extra_p.text = ""

    # 2. Update Skills in-place preserving runs
    skills = skills_section.get("highlighted", skills_section.get("all", []))
    if skills and "skills" in section_paragraphs and section_paragraphs["skills"]:
        skills_paras = section_paragraphs["skills"]
        skills_str = " • ".join(skills)
        if skills_paras[0].runs:
            skills_paras[0].runs[0].text = skills_str
            for r in skills_paras[0].runs[1:]:
                r.text = ""
        else:
            skills_paras[0].text = skills_str
        for extra_p in skills_paras[1:]:
            extra_p.text = ""

    # 3. Update Experience bullets in-place preserving runs
    if experience and "experience" in section_paragraphs and section_paragraphs["experience"]:
        exp_paras = section_paragraphs["experience"]
        all_bullets = []
        for item in experience:
            all_bullets.extend(item.get("bullets", []))

        bullet_idx = 0
        for para in exp_paras:
            if para.text.strip() and (para.style.name.startswith("List") or para.text.strip().startswith(("•", "-", "*")) or len(para.text.strip()) > 25):
                if bullet_idx < len(all_bullets):
                    new_bullet = all_bullets[bullet_idx]
                    bullet_idx += 1
                    prefix = "• " if para.text.strip().startswith("•") else ("- " if para.text.strip().startswith("-") else "")
                    full_txt = f"{prefix}{new_bullet}"
                    if para.runs:
                        para.runs[0].text = full_txt
                        for r in para.runs[1:]:
                            r.text = ""
                    else:
                        para.text = full_txt

    return True


def _build_doc_from_scratch(doc: Document, customized_content: dict, candidate_profile: dict, styles: dict) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(styles["margins"]["top"])
    section.bottom_margin = Inches(styles["margins"]["bottom"])
    section.left_margin = Inches(styles["margins"]["left"])
    section.right_margin = Inches(styles["margins"]["right"])

    _add_name_header(doc, candidate_profile, styles)

    summary = customized_content.get("summary", "")
    if summary:
        _add_summary(doc, summary, styles)

    skills_section = customized_content.get("skills_section", {})
    if skills_section:
        _add_skills(doc, skills_section, candidate_profile, styles)

    experience = customized_content.get("experience", [])
    _add_experience(doc, experience, candidate_profile, styles)


def generate_resume_docx(
    original_docx_bytes: bytes,
    customized_content: dict,
    candidate_profile: dict,
    job_title: str,
    company: str,
) -> bytes:
    """
    Generate a job-specific DOCX resume while preserving 100% of the Original DOCX Template style.
    Clones the master DOCX directly and performs in-place text updates to preserve fonts, sizes, colors,
    heading styles, borders, and margins.
    """
    styles = _get_doc_styles(original_docx_bytes)

    if original_docx_bytes:
        try:
            doc = Document(io.BytesIO(original_docx_bytes))
            updated = _update_doc_in_place(doc, customized_content, candidate_profile, styles)
            if updated:
                buf = io.BytesIO()
                doc.save(buf)
                return buf.getvalue()
        except Exception as e:
            logger.warning("[DOCXGenerator] In-place template update failed (%s), using scratch builder", e)

    doc = Document()
    _build_doc_from_scratch(doc, customized_content, candidate_profile, styles)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_resume_filename(
    candidate_profile: dict,
    company: str = "",
    job_title: str = "",
    extension: str = "docx",
) -> str:
    personal = (candidate_profile or {}).get("personal", {})
    full_name = personal.get("full_name") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    clean_name = re.sub(r"[^A-Za-z0-9]", "", full_name)
    if not clean_name:
        clean_name = "TamilselvanG"
    return f"{clean_name}_Resume.{extension}"
