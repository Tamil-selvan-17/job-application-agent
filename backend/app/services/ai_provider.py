"""
AI Provider abstraction.

Every other service in this app (resume analysis, ATS scoring, job
matching, cover letters, chat, etc.) should call `get_ai_provider()` and
use the returned object's `.generate(...)` method. It NEVER talks to
Ollama or Gemini directly. This is what lets you flip AI_PROVIDER in
.env (ollama <-> gemini) and have the entire app change AI backend with
no other code changes - just restart the server.

Gemini's MODEL, unlike the provider itself, is switchable live from the
UI (Settings tab) without a redeploy - see runtime_settings_service.py.
This is worth having because Gemini models intermittently return 503
(overloaded) or 429 (rate limited) - a well-documented, widespread issue
across all Gemini models, not specific to any one API key - and each
model has its OWN separate free-tier quota, so switching models is a
genuinely useful escape hatch, not just cosmetic.
"""
import asyncio
from abc import ABC, abstractmethod
import httpx

from app.config.env import env_settings
from app.services import runtime_settings_service

# Retry Gemini calls on transient overload/rate-limit errors before giving up.
GEMINI_RETRY_STATUS_CODES = {429, 503}
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_DELAY_SECONDS = 1.5


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None) -> str:
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        ...


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"ok": True, "provider": self.name, "models": models}
        except Exception as e:
            return {"ok": False, "provider": self.name, "error": str(e)}


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        if not self.api_key:
            raise ValueError(
                "Gemini API key is not set. Add it in Settings before using Gemini."
            )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        body = {"contents": [{"parts": [{"text": full_prompt}]}]}

        last_error: Exception | None = None
        for attempt in range(GEMINI_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(url, json=body)
                    if resp.status_code in GEMINI_RETRY_STATUS_CODES and attempt < GEMINI_MAX_RETRIES - 1:
                        await asyncio.sleep(GEMINI_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return ""
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in GEMINI_RETRY_STATUS_CODES and attempt < GEMINI_MAX_RETRIES - 1:
                    await asyncio.sleep(GEMINI_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Gemini request failed after retries")

    async def health_check(self) -> dict:
        if not self.api_key:
            return {"ok": False, "provider": self.name, "error": "No API key set"}
        try:
            await self.generate("ping", system="Reply with just: pong")
            return {"ok": True, "provider": self.name, "model": self.model}
        except Exception as e:
            return {"ok": False, "provider": self.name, "model": self.model, "error": str(e)}


async def get_effective_gemini_model() -> str:
    """The Gemini model actually in use: UI override if set, else the .env default."""
    overrides = await runtime_settings_service.get_overrides()
    return overrides.get("gemini_model") or env_settings.gemini_model


async def get_ai_provider() -> AIProvider:
    """
    Factory: reads AI_PROVIDER from .env (deliberately not UI-switchable -
    see project notes) and returns the active provider.

        AI_PROVIDER=ollama   -> uses OLLAMA_BASE_URL / OLLAMA_MODEL
        AI_PROVIDER=gemini   -> uses GEMINI_API_KEY + the effective model
                                 (UI override if set via Settings, else
                                 GEMINI_MODEL from .env)
    """
    provider = env_settings.ai_provider

    if provider == "gemini":
        model = await get_effective_gemini_model()
        return GeminiProvider(api_key=env_settings.gemini_api_key, model=model)
    # default / fallback
    return OllamaProvider(
        base_url=env_settings.ollama_base_url,
        model=env_settings.ollama_model,
    )
