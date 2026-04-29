from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    return await repos.app_settings.get_or_create(current_user.id)

@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    updates = {}
    if body.notifications_enabled is not None:
        updates["notifications_enabled"] = body.notifications_enabled
    if body.battery_mode is not None:
        updates["battery_mode"] = body.battery_mode
    if body.background_monitoring is not None:
        updates["background_monitoring"] = body.background_monitoring
    if body.update_interval_seconds is not None:
        updates["update_interval_seconds"] = body.update_interval_seconds

    result = await repos.app_settings.update(current_user.id, updates)
    await db.commit()
    return result
