"""
AI Provider abstraction.

Every other service in this app (resume analysis, ATS scoring, job
matching, cover letters, chat, etc.) should call `get_ai_provider()` and
use the returned object's `.generate(...)` method. It NEVER talks to
Ollama or Gemini directly. This is what lets you flip AI_PROVIDER in
.env (ollama <-> gemini) and have the entire app change AI backend with
no other code changes - just restart the server.
"""
from abc import ABC, abstractmethod
import httpx

from app.config.env import env_settings


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
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)

    async def health_check(self) -> dict:
        if not self.api_key:
            return {"ok": False, "provider": self.name, "error": "No API key set"}
        try:
            await self.generate("ping", system="Reply with just: pong")
            return {"ok": True, "provider": self.name}
        except Exception as e:
            return {"ok": False, "provider": self.name, "error": str(e)}


async def get_ai_provider() -> AIProvider:
    """
    Factory: reads AI_PROVIDER (and related keys) from .env and returns the
    active provider. To switch, edit .env and restart the server:

        AI_PROVIDER=ollama   -> uses OLLAMA_BASE_URL / OLLAMA_MODEL
        AI_PROVIDER=gemini   -> uses GEMINI_API_KEY / GEMINI_MODEL
    """
    provider = env_settings.ai_provider

    if provider == "gemini":
        return GeminiProvider(
            api_key=env_settings.gemini_api_key,
            model=env_settings.gemini_model,
        )
    # default / fallback
    return OllamaProvider(
        base_url=env_settings.ollama_base_url,
        model=env_settings.ollama_model,
    )
