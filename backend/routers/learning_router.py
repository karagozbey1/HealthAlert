from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import (
    ModelVersionResponse,
    TrainingExportRequest,
    TrainingExportResponse,
    UserFeedbackCreate,
    UserFeedbackResponse,
    LearningWindowResponse,
)
from services.learning_data_service import learning_data_service

logger = logging.getLogger("healthalert.learning_router")

router = APIRouter(prefix="/learning", tags=["learning-loop"])


# Yakalanan ogrenme pencerelerini filtrelerle listeler.
@router.get("/windows", response_model=List[LearningWindowResponse])
async def list_learning_windows(
    user_id: Optional[str] = Query(None, description="Filter by user"),
    training_candidate: Optional[bool] = Query(None, description="Filter by candidate flag"),
    source: Optional[str] = Query(None, description="Filter by source (live/demo/replay)"),
    limit: int = Query(100, ge=1, le=1000),
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        raise HTTPException(status_code=503, detail="Learning repository unavailable")
    windows = await repos.learning.list_windows(
        user_id=user_id,
        training_candidate=training_candidate,
        source=source,
        limit=limit,
    )
    return windows


# Tek bir ogrenme penceresinin ayrintisini dondurur.
@router.get("/windows/{window_id}", response_model=LearningWindowResponse)
async def get_learning_window(
    window_id: str,
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        raise HTTPException(status_code=503, detail="Learning repository unavailable")
    window = await repos.learning.get_window(window_id)
    if window is None:
        raise HTTPException(status_code=404, detail="Window not found")
    return window


# Ogrenme penceresi veya alert icin kullanici geri bildirimi kaydeder.
@router.post("/feedback", response_model=UserFeedbackResponse)
async def submit_feedback(
    body: UserFeedbackCreate,
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        raise HTTPException(status_code=503, detail="Learning repository unavailable")
    try:
        saved = await learning_data_service.attach_feedback(
            repos=repos,
            user_id=body.user_id,
            related_window_id=body.related_window_id,
            related_alert_id=body.related_alert_id,
            feedback_type=body.feedback_type,
            feedback_source=body.feedback_source,
            note=body.note,
        )
        return saved
    except Exception as exc:
        logger.error("Feedback submit error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save feedback")


# Egitime hazir pencereleri anonimlestirip JSONL olarak disa aktarir.
@router.post("/export", response_model=TrainingExportResponse)
async def export_training_data(
    body: TrainingExportRequest,
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        raise HTTPException(status_code=503, detail="Learning repository unavailable")
    try:
        summary = await learning_data_service.export_training_dataset(
            repos=repos,
            user_id=body.user_id,
            include_demo=body.include_demo,
            min_quality_confidence=body.min_quality_confidence,
            limit=body.limit,
        )
        return TrainingExportResponse(
            export_dir=summary["export_dir"],
            window_count=summary["window_count"],
            feedback_count=summary["feedback_count"],
            export_summary=summary,
        )
    except Exception as exc:
        logger.error("Export error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")


# Kullanici bazli ogrenme istatistiklerini dondurur.
@router.get("/summary/{user_id}")
async def learning_summary(
    user_id: str,
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        return {
            "user_id": user_id,
            "available": False,
            "reason": "learning repo unavailable",
        }
    return await learning_data_service.summarize_user_learning_data(
        repos=repos,
        user_id=user_id,
    )


# Kayitli model surumlerini salt-okunur olarak listeler.
@router.get("/model-versions", response_model=List[ModelVersionResponse])
async def list_model_versions(
    _current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if repos.learning is None:
        raise HTTPException(status_code=503, detail="Learning repository unavailable")
    return await repos.learning.list_model_versions()
