"""
PDF Generator Service — DOCX to PDF conversion.

Uses docx2pdf on Windows (calls MS Word COM automation).
Designed to be swappable: replace _convert_docx_to_pdf_impl() to switch
to LibreOffice or a cloud API without changing the public interface.

Returns PDF bytes (never writes to permanent disk — uses a temp file
that is cleaned up immediately after conversion).
"""
import io
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


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
    """Cross-platform fallback: LibreOffice headless."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "input.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        result = subprocess.run(
            [
                "libreoffice", "--headless", "--convert-to", "pdf",
                "--outdir", tmpdir, docx_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr.decode()}")

        pdf_path = os.path.join(tmpdir, "input.pdf")
        with open(pdf_path, "rb") as f:
            return f.read()


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Public interface. Tries docx2pdf first (Windows/MS Word), falls back to
    LibreOffice if docx2pdf is not available or running on non-Windows.

    Always runs synchronously (call via run_in_executor from async code).
    """
    import sys

    if sys.platform == "win32":
        try:
            import docx2pdf  # noqa: F401
            return _convert_via_docx2pdf(docx_bytes)
        except ImportError:
            logger.warning("docx2pdf not available on Windows, trying LibreOffice")
        except Exception as e:
            logger.warning("docx2pdf failed (%s), trying LibreOffice", e)
    else:
        logger.info("Non-Windows platform detected (%s), using LibreOffice for PDF conversion", sys.platform)

    return _convert_via_libreoffice(docx_bytes)
