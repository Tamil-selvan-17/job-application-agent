"""
Runs two daily jobs (per the spec's "Job Search Engine runs every day,
frequency configurable" and "HR Reminder"):

1. Job search across configured sources -> emails a digest if new jobs found
2. Follow-up check -> emails a reminder for applications past followup_after_days

Note: on Render's free tier the process spins down after ~15 min idle,
so these won't fire exactly on schedule unless something is actively
keeping the service awake (a paid "always on" plan, or an external
uptime pinger). Manual trigger endpoints exist for testing regardless.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config.env import env_settings
from app.services import job_search_service, job_service, email_service, config_service

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()


async def run_daily_search():
    try:
        result = await job_search_service.search_and_store_jobs()
        logger.info("Daily job search: %s", result)
        if result["new_jobs_added"] > 0:
            db_jobs = await job_service.list_jobs(status="new")
            newest = db_jobs[: result["new_jobs_added"]]
            await email_service.notify_new_jobs(newest)
    except Exception:
        logger.exception("Daily job search failed")


async def run_daily_followup_check():
    try:
        config = await config_service.get_config()
        days = int(config.get("followup_after_days", 5))
        due = await job_service.list_followups_due(days)
        if due:
            await email_service.notify_followups_due(due)
        logger.info("Follow-up check: %d due", len(due))
    except Exception:
        logger.exception("Daily follow-up check failed")


def start_scheduler():
    if not env_settings.enable_scheduler:
        logger.info("Scheduler disabled via ENABLE_SCHEDULER=false")
        return
    scheduler.add_job(
        run_daily_search,
        "cron",
        hour=env_settings.daily_search_hour_utc,
        id="daily_job_search",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_followup_check,
        "cron",
        hour=env_settings.daily_reminder_hour_utc,
        id="daily_followup_check",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
