"""
Runs two daily jobs:

1. Job search across configured sources -> emails a digest if new jobs found
2. Follow-up processing -> sends whichever reminder stage (1/2/3, at
   days 3/5/8 after applying) is newly due for each applied job, and
   auto-marks jobs "not_responded" at day 10 with no reply

Note: on Render's free tier the process spins down after ~15 min idle,
so these won't fire exactly on schedule unless something is actively
keeping the service awake (a paid "always on" plan, or an external
uptime pinger). Manual trigger endpoints exist for testing regardless.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config.env import env_settings
from app.services import job_search_service, job_service, email_service

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
        result = await job_service.process_followup_reminders()
        logger.info("Follow-up processing: %s", result)
    except Exception:
        logger.exception("Daily follow-up processing failed")


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
