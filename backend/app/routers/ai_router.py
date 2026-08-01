from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai_provider import get_ai_provider

router = APIRouter(prefix="/api/ai", tags=["ai"])


class GenerateRequest(BaseModel):
    prompt: str
    system: str | None = None


@router.post("/generate")
async def generate(req: GenerateRequest):
    """
    Generic passthrough to whichever AI provider is currently active
    (Ollama or Gemini, per Settings). Resume analysis, ATS scoring, cover
    letters, chat, etc. will all build on top of this same call.
    """
    provider = await get_ai_provider()
    try:
        result = await provider.generate(req.prompt, req.system)
    except Exception as e:
        raise HTTPException(502, f"AI provider ({provider.name}) error: {e}")
    return {"provider": provider.name, "response": result}
