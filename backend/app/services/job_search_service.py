"""
Orchestrates job search: reads the user's JSON config, pulls listings
from every configured source we support (see job_sources.py), filters
for relevance/location/language/job-type/experience/freshness, dedupes
against jobs already stored (by URL), and saves new ones. This is what
"Runs every day" in the spec plugs into - see scheduler_service.py.

Filter order (cheapest/most decisive first, so we don't waste work):
company blacklist/whitelist -> language -> exclude keywords ->
location -> job type -> experience -> posting freshness -> relevance
keyword-hit threshold -> duplicate check.
"""
from datetime import datetime, timezone

from app.database.mongo import get_db
from app.services import config_service
from app.services.job_sources import SOURCE_FETCHERS, UNIMPLEMENTED_SOURCES
from app.services.job_matching import (
    keyword_hits,
    matches_language,
    matches_location,
    matches_job_type,
    matches_experience,
    is_recent_enough,
    extract_email,
)

MIN_KEYWORD_HITS = 2  # require at least this many distinct skill/keyword matches to keep a job


async def search_and_store_jobs() -> dict:
    config = await config_service.get_config()
    db = get_db()

    requested_sources = config.get("job_sources") or list(SOURCE_FETCHERS.keys())
    active_sources = [s for s in requested_sources if s in SOURCE_FETCHERS]
    skipped_sources = [s for s in requested_sources if s in UNIMPLEMENTED_SOURCES]
    if not active_sources:
        active_sources = list(SOURCE_FETCHERS.keys())  # fall back to whatever's implemented

    skills = list(config.get("skills") or [])
    keywords_include = list(config.get("keywords_include") or [])
    keywords_exclude = list(config.get("keywords_exclude") or [])
    blacklist = [c.lower() for c in (config.get("company_blacklist") or [])]
    whitelist = [c.lower() for c in (config.get("company_whitelist") or [])]
    preferred_locations = list(config.get("preferred_locations") or [])
    preferred_job_types = list(config.get("job_types") or [])
    remote_ok = bool(config.get("remote", False))
    experience_max = config.get("experience_max")
    daily_limit = int(config.get("daily_job_limit", 50))
    job_posted_within_days = int(config.get("job_posted_within_days", 45))
    target_language = config.get("language") or "English"

    relevance_terms = list(dict.fromkeys(skills + keywords_include))  # dedup, keep order
    min_hits = min(MIN_KEYWORD_HITS, max(1, len(relevance_terms)))

    fetched: list[dict] = []
    errors: dict[str, str] = {}
    for source_name in active_sources:
        fetcher = SOURCE_FETCHERS[source_name]
        try:
            jobs = await fetcher(config)
            fetched.extend(jobs)
        except Exception as e:
            errors[source_name] = str(e)

    new_count = 0
    skipped_duplicate = 0
    skipped_irrelevant = 0
    skipped_language = 0
    skipped_location = 0
    skipped_job_type = 0
    skipped_experience = 0
    skipped_stale = 0
    skipped_filtered = 0

    for job in fetched:
        if new_count >= daily_limit:
            break

        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")
        description = job.get("description", "")
        location = job.get("location", "")
        job_type = job.get("job_type", "")
        posted_at = job.get("posted_at", "")
        if not url or not title:
            continue

        company_lower = company.lower()
        if blacklist and company_lower in blacklist:
            skipped_filtered += 1
            continue
        if whitelist and company_lower not in whitelist:
            skipped_filtered += 1
            continue

        haystack = f"{title} {description}"

        if not matches_language(haystack, target_language):
            skipped_language += 1
            continue

        if keywords_exclude and keyword_hits(haystack, keywords_exclude):
            skipped_filtered += 1
            continue

        if not matches_location(location, preferred_locations, remote_ok):
            skipped_location += 1
            continue

        if not matches_job_type(job_type, preferred_job_types):
            skipped_job_type += 1
            continue

        if not matches_experience(description, experience_max):
            skipped_experience += 1
            continue

        if not is_recent_enough(posted_at, max_age_days=job_posted_within_days):
            skipped_stale += 1
            continue

        if relevance_terms:
            hits = keyword_hits(haystack, relevance_terms)
            if len(hits) < min_hits:
                skipped_irrelevant += 1
                continue

        existing = await db.jobs.find_one({"url": url})
        if existing:
            skipped_duplicate += 1
            continue

        now = datetime.now(timezone.utc)
        await db.jobs.insert_one(
            {
                **job,
                "status": "new",
                "notes": "",
                "analysis": None,
                "hr_email_guess": extract_email(description),
                "created_at": now,
                "updated_at": now,
            }
        )
        new_count += 1

    return {
        "fetched_total": len(fetched),
        "new_jobs_added": new_count,
        "skipped_duplicate": skipped_duplicate,
        "skipped_irrelevant": skipped_irrelevant,
        "skipped_language": skipped_language,
        "skipped_location": skipped_location,
        "skipped_job_type": skipped_job_type,
        "skipped_experience": skipped_experience,
        "skipped_stale": skipped_stale,
        "skipped_filtered": skipped_filtered,
        "min_keyword_hits_required": min_hits,
        "target_language": target_language,
        "sources_used": active_sources,
        "sources_skipped_unimplemented": skipped_sources,
        "source_errors": errors,
        "ran_at": datetime.now(timezone.utc),
    }
