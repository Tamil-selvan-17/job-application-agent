import json
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.models.config_model import JobSearchConfig
from app.services import config_service

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=JobSearchConfig)
async def get_config():
    return await config_service.get_config()


@router.put("", response_model=JobSearchConfig)
async def replace_config(config: JobSearchConfig):
    """Full replace - send the entire config object."""
    return await config_service.replace_config(config.model_dump())


@router.patch("", response_model=JobSearchConfig)
async def patch_config(patch: dict):
    """Partial update - send only the fields you want to change."""
    return await config_service.patch_config(patch)


@router.post("/upload", response_model=JobSearchConfig)
async def upload_config(file: UploadFile = File(...)):
    """Upload a .json file to replace the current config entirely."""
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Please upload a .json file")
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")
    return await config_service.replace_config(data)
