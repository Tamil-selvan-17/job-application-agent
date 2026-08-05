from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_provider import get_ai_provider, get_effective_gemini_model
from app.services import runtime_settings_service
from app.config.env import env_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Common current Gemini model names. Newer 3.x preview models may not be
# available to every API key yet, so the 2.5 series is listed first as
# the safest default set - all confirmed stable and generally available.
GEMINI_MODEL_CHOICES = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]


class GeminiModelUpdate(BaseModel):
    model: str


@router.get("")
async def get_settings():
    """
    AI provider (Ollama vs Gemini) stays .env-only by design - no UI
    toggle for that. The Gemini MODEL, however, is switchable live from
    the UI (see PUT /gemini-model) since models intermittently return
    503/429 and each has its own separate quota - being stuck on one
    until a redeploy isn't useful.
    """
    effective_model = await get_effective_gemini_model()
    return {
        "ai_provider": env_settings.ai_provider,
        "ollama_base_url": env_settings.ollama_base_url,
        "ollama_model": env_settings.ollama_model,
        "gemini_model": effective_model,
        "gemini_model_is_override": effective_model != env_settings.gemini_model,
        "gemini_model_env_default": env_settings.gemini_model,
        "gemini_model_choices": GEMINI_MODEL_CHOICES,
        "gemini_api_key_set": bool(env_settings.gemini_api_key),
    }


@router.put("/gemini-model")
async def set_gemini_model(req: GeminiModelUpdate):
    """
    Switches the Gemini model used for all AI calls immediately - no
    redeploy needed. Persists in Mongo, so it survives restarts. Doesn't
    validate the model name against Google's API here (that would cost
    an extra call) - use Test Connection right after switching to confirm
    it actually works.
    """
    await runtime_settings_service.set_override("gemini_model", req.model)
    return await get_settings()


@router.get("/ai/health")
async def ai_health():
    """Check whether the currently active AI provider+model is reachable."""
    provider = await get_ai_provider()
    return await provider.health_check()
