from fastapi import APIRouter

from app.services.ai_provider import get_ai_provider
from app.config.env import env_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    """
    AI provider is configured purely via .env now (AI_PROVIDER=ollama|gemini
    + related keys) - no UI toggle. This just reports what's active so the
    frontend can show it read-only.
    """
    return {
        "ai_provider": env_settings.ai_provider,
        "ollama_base_url": env_settings.ollama_base_url,
        "ollama_model": env_settings.ollama_model,
        "gemini_model": env_settings.gemini_model,
        "gemini_api_key_set": bool(env_settings.gemini_api_key),
    }


@router.get("/ai/health")
async def ai_health():
    """Check whether the currently active AI provider (Ollama or Gemini, per .env) is reachable."""
    provider = await get_ai_provider()
    return await provider.health_check()
