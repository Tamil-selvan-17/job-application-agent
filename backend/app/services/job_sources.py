"""
Job source connectors. Each function takes the full Job Search Config
dict and returns raw listings normalized to:

    {title, company, description, location, url, source, salary_text,
     job_type, posted_at}

(job_type/posted_at may be empty/None if the source doesn't provide them
- callers should treat missing values as "unknown, don't over-filter".)

Currently wired:
- Remotive, Arbeitnow: free, public, no-login JSON APIs, no scraping/ToS
  risk - but both are Western remote-job boards with very little India
  coverage.
- Adzuna: free, keyed API (https://developer.adzuna.com/, sign up free)
  that actually indexes India and most other countries, and supports
  location + recency filtering server-side. Set ADZUNA_APP_ID/
  ADZUNA_APP_KEY in .env to enable it - it's skipped silently if unset.

LinkedIn/Indeed/Naukri/Wellfound require browser automation (login,
sessions, CAPTCHA) which is a much bigger and riskier piece (account
bans, ToS violations) - that's a separate future stage (Playwright-based
scraper), not built here.

Relevance/location/language/experience filtering is centralized in
job_search_service.py via job_matching.py, NOT done here - these
functions just fetch and normalize.

To add a new source: write `fetch_x(config: dict) -> list[dict]`
returning the normalized shape above, then register it in
SOURCE_FETCHERS at the bottom of this file.
"""
import re
import asyncio
from datetime import datetime, timezone
import httpx

from app.config.env import env_settings

REQUEST_TIMEOUT = 20

# Remotive explicitly asks for max ~2 requests/minute and ~4/day total -
# https://github.com/remotive-com/remote-jobs-api. Keep queries per run low
# and spaced out to stay a good citizen of their free public API.
REMOTIVE_MAX_QUERIES_PER_RUN = 2
ADZUNA_MAX_QUERIES_PER_RUN = 2


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _search_terms(config: dict, cap: int) -> list[str]:
    terms = list(config.get("keywords_include") or []) or list(config.get("skills") or [])
    terms = [t for t in terms if t and t.strip()]
    return terms[:cap] if terms else [""]


async def fetch_remotive(config: dict) -> list[dict]:
    """
    https://remotive.com/api/remote-jobs - free, no auth, remote jobs only
    by nature. Runs one query per top keyword (capped) rather than joining
    several keywords into one search string, since Remotive's search
    doesn't reliably OR/AND multi-word queries - and merges/dedupes results.
    """
    terms = _search_terms(config, REMOTIVE_MAX_QUERIES_PER_RUN)
    seen_urls: set[str] = set()
    jobs: list[dict] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for i, term in enumerate(terms):
            params = {"limit": 50}
            if term:
                params["search"] = term
            resp = await client.get("https://remotive.com/api/remote-jobs", params=params)
            resp.raise_for_status()
            data = resp.json()
            for j in data.get("jobs", []):
                url = j.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append(
                    {
                        "title": j.get("title", ""),
                        "company": j.get("company_name", ""),
                        "description": _strip_html(j.get("description", "")),
                        # Every Remotive listing is remote by definition, but this field
                        # often reads like "Northern America, Europe, APAC" without the
                        # literal word "remote" - prefix it so downstream location
                        # matching (which looks for "remote") reliably recognizes it.
                        "location": f"Remote ({j.get('candidate_required_location', 'Anywhere')})",
                        "url": url,
                        "source": "Remotive",
                        "salary_text": j.get("salary", "") or "",
                        "job_type": j.get("job_type", "") or "",
                        "posted_at": j.get("publication_date", "") or "",
                    }
                )
            if i < len(terms) - 1:
                await asyncio.sleep(1)  # stay well under the rate limit between calls

    return jobs


async def fetch_arbeitnow(config: dict) -> list[dict]:
    """
    https://www.arbeitnow.com/api/job-board-api - free, no auth. Returns
    every active listing unfiltered (no remote_only cutoff here anymore -
    that was wrongly discarding valid on-site matches; location handling
    now happens centrally in job_search_service.py so "remote OR my
    preferred city" both get a chance).
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get("https://www.arbeitnow.com/api/job-board-api")
        resp.raise_for_status()
        data = resp.json()

    jobs = []
    for j in data.get("data", []):
        job_types = j.get("job_types") or []
        jobs.append(
            {
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "description": _strip_html(j.get("description", "")),
                "location": j.get("location", "") or ("Remote" if j.get("remote") else ""),
                "url": j.get("url", ""),
                "source": "Arbeitnow",
                "salary_text": "",
                "job_type": ", ".join(job_types) if job_types else "",
                "posted_at": _unix_to_iso(j.get("created_at")),
            }
        )
    return jobs


def _unix_to_iso(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return ""


async def fetch_adzuna(config: dict) -> list[dict]:
    """
    https://developer.adzuna.com/ - free, keyed API. Actually indexes
    India (and most countries) with real location + recency filtering
    server-side, unlike Remotive/Arbeitnow. Requires a free API key -
    sign up at developer.adzuna.com, then set ADZUNA_APP_ID and
    ADZUNA_APP_KEY in .env. Silently returns [] (not an error) if unset,
    since this is an opt-in source.
    """
    if not env_settings.adzuna_app_id or not env_settings.adzuna_app_key:
        return []

    terms = _search_terms(config, ADZUNA_MAX_QUERIES_PER_RUN)
    preferred_locations = list(config.get("preferred_locations") or [])
    remote_ok = bool(config.get("remote", False))
    # Search once per preferred location if any are set, otherwise one
    # unscoped query (relies on remote/relevance filtering downstream).
    locations = preferred_locations if preferred_locations else [""]

    country = env_settings.adzuna_country
    seen_ids: set[str] = set()
    jobs: list[dict] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for term in terms:
            for where in locations:
                params = {
                    "app_id": env_settings.adzuna_app_id,
                    "app_key": env_settings.adzuna_app_key,
                    "results_per_page": 30,
                    "content-type": "application/json",
                    "max_days_old": 30,
                }
                if term:
                    params["what"] = term
                if where:
                    params["where"] = where
                try:
                    resp = await client.get(
                        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    continue  # one bad combo shouldn't kill the whole source

                for j in data.get("results", []):
                    job_id = str(j.get("id", ""))
                    url = j.get("redirect_url", "")
                    if not url or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    loc = j.get("location", {}).get("display_name", "") if j.get("location") else ""
                    salary_min = j.get("salary_min")
                    salary_max = j.get("salary_max")
                    salary_text = ""
                    if salary_min or salary_max:
                        salary_text = f"{salary_min or ''}-{salary_max or ''}".strip("-")
                    jobs.append(
                        {
                            "title": j.get("title", ""),
                            "company": (j.get("company") or {}).get("display_name", ""),
                            "description": _strip_html(j.get("description", "")),
                            "location": loc or ("Remote" if remote_ok else ""),
                            "url": url,
                            "source": "Adzuna",
                            "salary_text": salary_text,
                            "job_type": (j.get("contract_time") or "") + (
                                f", {j.get('contract_type')}" if j.get("contract_type") else ""
                            ),
                            "posted_at": j.get("created", "") or "",
                        }
                    )
                await asyncio.sleep(0.3)

    return jobs


# Register new sources here: name -> fetcher fn (fetcher receives the full config dict)
SOURCE_FETCHERS = {
    "Remotive": fetch_remotive,
    "Arbeitnow": fetch_arbeitnow,
    "Adzuna": fetch_adzuna,
}

# Sources listed in the spec that need browser automation (Playwright) - not implemented yet.
# Kept here so the search step can report clearly what it skipped instead of silently doing nothing.
UNIMPLEMENTED_SOURCES = {"LinkedIn", "Indeed", "Naukri", "Wellfound", "Foundit", "Greenhouse", "Lever"}
