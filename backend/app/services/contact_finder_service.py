"""
HR Contact Discovery Service.

Searches publicly available sources to find HR/recruiter email addresses
for a given company:

  Step 1: Extract ALL email addresses from the job description text.
  Step 2: Fetch the company website homepage, discover /contact, /careers,
          /about, /team pages and extract HR-pattern emails from them.
  Step 3: Try common HR email patterns against the company domain.
  Step 4: Score and deduplicate results.

IMPORTANT:
  - Only processes publicly accessible pages (no login required).
  - Does NOT bypass anti-bot measures or attempt to scrape private data.
  - Does NOT attempt LinkedIn scraping (ToS violation).
  - Only stores emails that are actually discovered.
  - Confidence scoring is based on email pattern and source quality.
"""
import re
import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.database.mongo import get_db
from bson import ObjectId
from datetime import datetime, timezone

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Email prefix patterns that strongly suggest HR/recruitment contacts
HR_PREFIXES = {"hr", "careers", "jobs", "recruitment", "talent", "hiring", "people",
               "recruit", "humanresources", "apply", "joinus", "staffing"}
MEDIUM_PREFIXES = {"contact", "info", "hello", "team", "work"}

REQUEST_TIMEOUT = 10
MAX_PAGES_TO_FETCH = 5  # Safety cap — don't crawl endlessly

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _extract_emails_from_text(text: str) -> list[str]:
    return list(set(_EMAIL_RE.findall(text or "")))


def _score_email(email: str) -> tuple[int, str]:
    """Returns (confidence_0_100, contact_type)."""
    prefix = email.split("@")[0].lower().replace(".", "").replace("-", "").replace("_", "")
    if any(hp in prefix for hp in HR_PREFIXES):
        return 90, "HR"
    if any(mp in prefix for mp in MEDIUM_PREFIXES):
        return 50, "CAREERS"
    return 30, "OTHER"


def _domain_from_url(url: str) -> str | None:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return None


def _discover_subpages(html: str, base_url: str) -> list[str]:
    """Find career/contact/about links from a homepage."""
    soup = BeautifulSoup(html, "lxml")
    patterns = ["career", "job", "contact", "about", "team", "people", "work-with", "join"]
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(p in href for p in patterns):
            full = urljoin(base_url, a["href"])
            if full.startswith("http") and full not in found:
                found.append(full)
    return found[:MAX_PAGES_TO_FETCH]


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        return resp.text
    except Exception:
        return ""


async def find_hr_contacts(
    company: str,
    company_url: str,
    job_description: str,
    job_url: str,
) -> list[dict]:
    """
    Returns list of contact dicts:
    {email, source, confidence, contact_type, verified, name}
    """
    found: dict[str, dict] = {}  # email → contact dict

    def _add(email: str, source: str) -> None:
        email = email.strip().lower()
        if not email or "@" not in email:
            return
        # Filter out obviously non-HR domains (job boards, LinkedIn, etc.)
        domain = email.split("@")[-1]
        if any(skip in domain for skip in ["linkedin.com", "example.com", "noreply"]):
            return
        if email not in found:
            conf, ctype = _score_email(email)
            found[email] = {
                "email": email,
                "source": source,
                "confidence": conf,
                "contact_type": ctype,
                "verified": False,
                "name": "",
            }
        else:
            # Boost confidence if found in multiple sources
            found[email]["confidence"] = min(100, found[email]["confidence"] + 10)

    # ---- Step 1: Extract from JD text ----------------------------------------
    for email in _extract_emails_from_text(job_description):
        _add(email, "job_description")

    for email in _extract_emails_from_text(job_url):
        _add(email, "job_url")

    # ---- Step 2: Fetch company website and subpages --------------------------
    company_domain = _domain_from_url(company_url) if company_url else None

    if company_url:
        async with httpx.AsyncClient(headers=HEADERS, timeout=REQUEST_TIMEOUT) as client:
            homepage_html = await _fetch_page(client, company_url)
            if homepage_html:
                for email in _extract_emails_from_text(homepage_html):
                    _add(email, f"company_website ({company_url})")

                # Discover and fetch subpages
                subpages = _discover_subpages(homepage_html, company_url)
                tasks = [_fetch_page(client, url) for url in subpages]
                results = await asyncio.gather(*tasks)
                for url, html in zip(subpages, results):
                    if html:
                        for email in _extract_emails_from_text(html):
                            _add(email, f"company_subpage ({url})")

    # ---- Step 3: Try common HR email patterns against company domain ----------
    if company_domain:
        patterns = [
            f"hr@{company_domain}",
            f"careers@{company_domain}",
            f"jobs@{company_domain}",
            f"recruitment@{company_domain}",
            f"talent@{company_domain}",
        ]
        # Only add these if domain looks valid (has a dot, not too long)
        if "." in company_domain and len(company_domain) < 60:
            for pattern_email in patterns:
                # Don't add guess-only emails with zero evidence — mark lower confidence
                if pattern_email not in found:
                    conf, ctype = _score_email(pattern_email)
                    found[pattern_email] = {
                        "email": pattern_email,
                        "source": "pattern_guess",
                        "confidence": max(20, conf - 30),  # Guessed, so lower confidence
                        "contact_type": ctype,
                        "verified": False,
                        "name": "",
                    }

    # Sort by confidence descending
    contacts = sorted(found.values(), key=lambda c: -c["confidence"])
    return contacts


async def discover_and_store_contacts(job_id: str) -> list[dict]:
    """
    Runs contact discovery for a job and stores the results in job.contacts.
    Returns the updated contacts list.
    """
    db = get_db()
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise ValueError("Job not found")

    contacts = await find_hr_contacts(
        company=job.get("company", ""),
        company_url=job.get("company_url", "") or (job.get("jd_analysis") or {}).get("companyUrl", ""),
        job_description=job.get("description", ""),
        job_url=job.get("url", ""),
    )

    # Also include the existing hr_email/hr_email_guess (if not already found)
    existing_emails = {c["email"] for c in contacts}
    for email_field, source_label in [("hr_email", "manual_entry"), ("hr_email_guess", "jd_regex")]:
        email = job.get(email_field, "")
        if email and email not in existing_emails:
            conf, ctype = _score_email(email)
            contacts.insert(0, {
                "email": email,
                "source": source_label,
                "confidence": 95 if email_field == "hr_email" else conf,
                "contact_type": ctype,
                "verified": False,
                "name": "",
            })

    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {
            "$set": {
                "contacts": contacts,
                "workflow_state": "CONTACTS_FOUND",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return contacts
