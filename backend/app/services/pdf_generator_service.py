import io
import os
import shutil
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _find_libreoffice_binary() -> str | None:
    """Finds libreoffice or soffice executable path if available."""
    for cmd in ["libreoffice", "soffice", "libreoffice7.6", "libreoffice7.5"]:
        path = shutil.which(cmd)
        if path:
            return path
    return None


def _convert_via_docx2pdf(docx_bytes: bytes) -> bytes:
    """Windows path: docx2pdf via MS Word COM."""
    from docx2pdf import convert
    import pythoncom

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "input.docx")
        pdf_path = os.path.join(tmpdir, "input.pdf")

        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        # Initialize COM for this thread (required when called from thread pool)
        pythoncom.CoInitialize()
        try:
            convert(docx_path, pdf_path)
        finally:
            pythoncom.CoUninitialize()

        with open(pdf_path, "rb") as f:
            return f.read()


def _convert_via_libreoffice(docx_bytes: bytes) -> bytes:
    """Cross-platform fallback: LibreOffice headless CLI."""
    import subprocess

    cmd = _find_libreoffice_binary()
    if not cmd:
        raise FileNotFoundError("LibreOffice binary not found in PATH")

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "input.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        result = subprocess.run(
            [
                cmd, "--headless", "--convert-to", "pdf",
                "--outdir", tmpdir, docx_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr.decode()}")

        pdf_path = os.path.join(tmpdir, "input.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("LibreOffice conversion produced no output PDF file")

        with open(pdf_path, "rb") as f:
            return f.read()


import html as html_module
import re


def _paragraph_to_reportlab_html(p) -> str:
    """
    Parses python-docx Paragraph elements (<w:r> runs and <w:hyperlink> nodes) into
    ReportLab HTML-compatible text, preserving bold/italic/colors and active <a href="..."> links.
    """
    html_parts = []

    for child in p._p:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "hyperlink":
            r_id = child.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            url = ""
            if r_id and hasattr(p.part, 'rels') and r_id in p.part.rels:
                url = p.part.rels[r_id].target_ref

            link_text = "".join(node.text for node in child.iter() if node.tag.endswith("t")).strip()
            escaped_text = html_module.escape(link_text)

            if not url:
                lt_lower = link_text.lower()
                if "linkedin" in lt_lower: url = "https://linkedin.com"
                elif "github" in lt_lower: url = "https://github.com"
                elif "portfolio" in lt_lower: url = "https://portfolio.dev"
                elif "@" in lt_lower: url = f"mailto:{link_text}"

            if url and link_text:
                if not url.startswith("http") and not url.startswith("mailto:"):
                    url = f"https://{url}"
                html_parts.append(f'<font color="#1d4ed8"><u><a href="{url}">{escaped_text}</a></u></font>')
            elif link_text:
                html_parts.append(escaped_text)

        elif tag == "r":
            text_nodes = [node.text for node in child.iter() if node.tag.endswith("t")]
            text = "".join(text_nodes)
            if not text:
                continue

            escaped = html_module.escape(text)

            rPr = child.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr")
            is_bold = rPr is not None and (rPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}b") is not None)
            is_italic = rPr is not None and (rPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}i") is not None)

            color_hex = None
            if rPr is not None:
                color_node = rPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color")
                if color_node is not None:
                    c_val = color_node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                    if c_val and c_val != "auto" and len(c_val) == 6:
                        color_hex = f"#{c_val}"

            # Auto-link raw URLs / emails in run text
            if "@" in escaped and "<a href=" not in escaped:
                escaped = re.sub(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", r'<font color="#1d4ed8"><u><a href="mailto:\1">\1</a></u></font>', escaped)

            if is_bold:
                escaped = f"<b>{escaped}</b>"
            if is_italic:
                escaped = f"<i>{escaped}</i>"
            if color_hex:
                escaped = f'<font color="{color_hex}">{escaped}</font>'

            html_parts.append(escaped)

    return "".join(html_parts)


def _convert_via_reportlab(docx_bytes: bytes) -> bytes:
    """
    Pure-Python fallback when docx2pdf and LibreOffice CLI binaries are unavailable.
    Parses docx paragraphs/tables using python-docx and builds a clean PDF via ReportLab
    preserving active links, bold formatting, section borders, and font colors.
    """
    import docx
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    doc = docx.Document(io.BytesIO(docx_bytes))
    buffer = io.BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2,
    )
    section_heading_style = ParagraphStyle(
        'DocSectionHeading',
        parent=styles['Heading2'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=normal_style,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=3,
    )
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=14,
        spaceAfter=2,
    )

    story = []

    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue

        html_text = _paragraph_to_reportlab_html(p)
        style_name = p.style.name.lower() if p.style else ""

        is_heading = any(h in txt.upper() for h in ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"]) and len(txt) < 45

        if "title" in style_name or ("name" in style_name and len(txt) < 35):
            story.append(Paragraph(html_text, title_style))
        elif is_heading:
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"<b>{txt.upper()}</b>", section_heading_style))
            # Solid section bottom border line
            t = Table([[""]], colWidths=[540], rowHeights=[1.5])
            t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0f172a'))]))
            story.append(t)
            story.append(Spacer(1, 3))
        elif p.style.name.startswith("List") or txt.startswith(("•", "-", "*")):
            clean_txt = re.sub(r"^[•\-\*\s]+", "", html_text).strip()
            story.append(Paragraph(f"&bull; {clean_txt}", bullet_style))
        else:
            story.append(Paragraph(html_text, body_style))

    for table in doc.tables:
        table_data = []
        for row in table.rows:
            row_data = [Paragraph(_paragraph_to_reportlab_html(cell.paragraphs[0]) if cell.paragraphs else cell.text.strip(), body_style) for cell in row.cells]
            table_data.append(row_data)
        if table_data:
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0f172a')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))

    if not story:
        story.append(Paragraph("Resume Document", title_style))

    pdf_doc.build(story)
    return buffer.getvalue()


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Public interface.
    1. Try docx2pdf (Windows/MS Word) if on Windows.
    2. Try LibreOffice/soffice if binary exists on system PATH.
    3. Fall back to pure-Python ReportLab conversion (works on any OS/Render without binaries).
    """
    import sys

    if sys.platform == "win32":
        try:
            import docx2pdf  # noqa: F401
            return _convert_via_docx2pdf(docx_bytes)
        except ImportError:
            logger.warning("docx2pdf not available on Windows, trying alternatives...")
        except Exception as e:
            logger.warning("docx2pdf failed (%s), trying alternatives...", e)

    # Check for LibreOffice binary
    if _find_libreoffice_binary():
        try:
            logger.info("Converting DOCX to PDF using LibreOffice")
            return _convert_via_libreoffice(docx_bytes)
        except Exception as e:
            logger.warning("LibreOffice conversion failed (%s), trying pure-Python fallback...", e)

    # Fall back to ReportLab pure Python conversion
    logger.info("Using pure-Python ReportLab PDF conversion fallback")
    try:
        return _convert_via_reportlab(docx_bytes)
    except Exception as e:
        logger.error("ReportLab conversion failed: %s", e)
        raise RuntimeError(f"PDF conversion failed: {e}")


def generate_cover_letter_pdf(candidate_profile: dict, job_title: str, company: str, cover_letter_text: str) -> bytes:
    """
    Generates a professional 1-page Cover Letter PDF matching the candidate profile styling.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    normal = styles['Normal']

    personal = (candidate_profile or {}).get("personal", {})
    name = personal.get("full_name", "") or "TAMILSELVAN G"
    phone = personal.get("phone", "") or "+91 7200206323"
    email = personal.get("email", "") or "tamilselvang0002@gmail.com"
    location = personal.get("location", "") or "Chennai, India"

    title_style = ParagraphStyle(
        'CLTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        'CLSub', parent=normal, fontSize=10.5, leading=14, textColor=colors.HexColor("#1d4ed8"), spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        'CLMeta', parent=normal, fontSize=9.5, leading=13, textColor=colors.HexColor("#475569"), spaceAfter=10,
    )
    body_style = ParagraphStyle(
        'CLBody', parent=normal, fontSize=10.5, leading=15, textColor=colors.HexColor("#1e293b"), spaceAfter=8,
    )

    story = []
    story.append(Paragraph(f"<b>{html_module.escape(name.upper())}</b>", title_style))
    story.append(Paragraph(f"<b>Full Stack Software Engineer | Cover Letter</b>", sub_style))
    story.append(Paragraph(f"{html_module.escape(phone)} | <font color='#1d4ed8'><u><a href='mailto:{html_module.escape(email)}'>{html_module.escape(email)}</a></u></font> | {html_module.escape(location)}", meta_style))

    t = Table([[""]], colWidths=[540], rowHeights=[1.5])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0f172a'))]))
    story.append(t)
    story.append(Spacer(1, 14))

    today_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(today_str, body_style))
    story.append(Paragraph(f"<b>Hiring Manager / Talent Acquisition Team</b><br/>{html_module.escape(company)}", body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph(f"<b>RE: Application for {html_module.escape(job_title)} Position</b>", body_style))
    story.append(Spacer(1, 6))

    paragraphs = [p.strip() for p in cover_letter_text.split("\n\n") if p.strip()]
    for p_text in paragraphs:
        escaped_p = html_module.escape(p_text)
        story.append(Paragraph(escaped_p, body_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Sincerely,<br/><b>" + html_module.escape(name) + "</b>", body_style))

    pdf_doc.build(story)
    return buffer.getvalue()

