"""Candidate profile API — get/save the single candidate profile document."""
from fastapi import APIRouter, HTTPException
from app.services import candidate_service

router = APIRouter(prefix="/api/candidate", tags=["candidate"])


@router.get("")
async def get_profile():
    return await candidate_service.get_profile()


@router.put("")
async def save_profile(data: dict):
    return await candidate_service.save_profile(data)


@router.patch("")
async def patch_profile(data: dict):
    return await candidate_service.patch_profile(data)
