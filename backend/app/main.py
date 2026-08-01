from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database.mongo import connect_to_mongo, close_mongo_connection
from app.routers import (
    config_router,
    settings_router,
    ai_router,
    resume_router,
    job_router,
    jobsearch_router,
    notifications_router,
    cover_letter_router,
)
from app.services.scheduler_service import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_to_mongo()
    start_scheduler()
    yield
    stop_scheduler()
    close_mongo_connection()


app = FastAPI(
    title="AI Job Application Agent",
    description="Core API: settings, AI provider switch (Ollama/Gemini), job-search config.",
    version="0.1.0",
    lifespan=lifespan,
)

# No auth for now (single-user local setup) - CORS wide open for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config_router.router)
app.include_router(settings_router.router)
app.include_router(ai_router.router)
app.include_router(resume_router.router)
app.include_router(cover_letter_router.router)
app.include_router(job_router.router)
app.include_router(jobsearch_router.router)
app.include_router(notifications_router.router)

# Serve the plain HTML/Bootstrap/JS frontend at /
# Resolved absolutely (not "../frontend") so this works no matter what the
# process's working directory is - important on Render, where the start
# command may run from the repo root rather than backend/.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Bump this string every time you ship a change. Check it after a deploy
# (GET /api/version, or the small badge in the UI footer) to confirm
# Render is actually running the code you think it is - saves a lot of
# guessing when something "doesn't seem to have the fix."
APP_VERSION = "stage7.3-brevo-permanent-free-email"


@app.get("/api/version")
async def version():
    return {"version": APP_VERSION}
