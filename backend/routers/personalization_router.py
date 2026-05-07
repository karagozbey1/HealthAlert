from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import (
    PersonalHealthProfileResponse,
    PersonalizationSummaryResponse,
    PersonalRiskMemoryResponse,
    PersonalTrendSnapshotResponse,
)
from services.adaptive_personalization_service import adaptive_personalization_service

logger = logging.getLogger("personalization_router")

router = APIRouter(prefix="/personalization", tags=["personalization"])


# Kullanici icin profil kaydini getirir veya olusturur.
@router.get("/profile/{user_id}", response_model=PersonalHealthProfileResponse)
async def get_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
    current_user: User = Depends(get_current_user),
):
    if repos.personalization is None:
        raise HTTPException(status_code=503, detail="Personalization not available in this data mode.")
    profile = await adaptive_personalization_service.get_or_create_profile(repos, user_id)
    return profile


# Kullanici icin ozet kisisellestirme istatistiklerini dondurur.
@router.get("/summary/{user_id}", response_model=PersonalizationSummaryResponse)
async def get_summary(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
    current_user: User = Depends(get_current_user),
):
    if repos.personalization is None:
        raise HTTPException(status_code=503, detail="Personalization not available in this data mode.")
    summary = await adaptive_personalization_service.get_personalization_summary(repos, user_id)
    return summary


# Kullaniciya ait son trend anlik goruntusunu getirir.
@router.get("/trends/{user_id}", response_model=PersonalTrendSnapshotResponse)
async def get_latest_trend(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
    current_user: User = Depends(get_current_user),
):
    if repos.personalization is None:
        raise HTTPException(status_code=503, detail="Personalization not available in this data mode.")
    try:
        trend = await repos.personalization.get_latest_trend_snapshot(user_id)
    except Exception as exc:
        logger.warning("get_latest_trend_snapshot failed for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve trend data.")
    if trend is None:
        raise HTTPException(status_code=404, detail="No trend snapshots found for this user.")
    return trend


# Kullaniciya ait risk hafizasi kayitlarini listeler.
@router.get("/memory/{user_id}", response_model=List[PersonalRiskMemoryResponse])
async def get_risk_memory(
    user_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
    current_user: User = Depends(get_current_user),
):
    if repos.personalization is None:
        raise HTTPException(status_code=503, detail="Personalization not available in this data mode.")
    limit = max(1, min(500, limit))
    try:
        memory = await repos.personalization.list_risk_memory(user_id, limit=limit)
    except Exception as exc:
        logger.warning("list_risk_memory failed for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve risk memory.")
    return memory
