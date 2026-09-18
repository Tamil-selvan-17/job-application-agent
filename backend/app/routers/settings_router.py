import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai_provider import get_ai_provider, get_effective_gemini_model
from app.services import runtime_settings_service
from app.config.env import env_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Comprehensive list of stable and preview free Gemini models
GEMINI_MODEL_CHOICES = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash-8b",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-pro-preview-06-05",
]


async def fetch_available_gemini_models() -> list[str]:
    """Fetch live list of available generation models from Gemini API if API key is set."""
    key = env_settings.gemini_api_key
    if not key:
        return GEMINI_MODEL_CHOICES

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                fetched = []
                for m in data.get("models", []):
                    name = m.get("name", "").replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and not any(x in name.lower() for x in ["embedding", "imagen", "aqa", "bison"]):
                        fetched.append(name)
                if fetched:
                    # Combine fetched models with default choices without duplicates
                    return list(dict.fromkeys(fetched + GEMINI_MODEL_CHOICES))
    except Exception as e:
        logger.warning("[SettingsRouter] Error fetching models from Gemini API: %s", e)

    return GEMINI_MODEL_CHOICES


class GeminiModelUpdate(BaseModel):
    model: str | None = None
    gemini_model: str | None = None


@router.get("")
async def get_settings():
    """
    Returns current AI settings, active model, and available Gemini models list.
    """
    effective_model = await get_effective_gemini_model()
    choices = await fetch_available_gemini_models()
    return {
        "ai_provider": env_settings.ai_provider,
        "ollama_base_url": env_settings.ollama_base_url,
        "ollama_model": env_settings.ollama_model,
        "gemini_model": effective_model,
        "gemini_model_is_override": effective_model != env_settings.gemini_model,
        "gemini_model_env_default": env_settings.gemini_model,
        "gemini_model_choices": choices,
        "gemini_api_key_set": bool(env_settings.gemini_api_key),
    }


@router.put("")
@router.put("/gemini-model")
async def set_gemini_model(req: GeminiModelUpdate):
    """
    Switches the Gemini model used for all AI calls immediately.
    Accepts { gemini_model: "..." } or { model: "..." }.
    """
    chosen_model = req.gemini_model or req.model
    if not chosen_model:
        raise HTTPException(400, "Field 'gemini_model' or 'model' is required.")

    await runtime_settings_service.set_override("gemini_model", chosen_model)
    return await get_settings()


@router.get("/gemini-models")
async def get_gemini_models():
    """Returns the list of available Gemini models."""
    choices = await fetch_available_gemini_models()
    return {"models": choices}


@router.get("/ai/health")
@router.get("/health")
async def ai_health():
    """Check whether the currently active AI provider+model is reachable."""
    provider = await get_ai_provider()
    res = await provider.health_check()
    res["status"] = "ok" if res.get("ok") else "error"
    return res
