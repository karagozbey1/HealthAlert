from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DeviceToken, User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import DeviceTokenResponse, NotificationResponse, RegisterDeviceTokenRequest

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Mevcut kullaniciya ait bildirimleri listeler.
@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    return await repos.notifications.list_by_recipient(current_user.id)

# Mevcut kullanicinin tum bildirimlerini okundu isaretler.
@router.put("/read-all", status_code=204)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    await repos.notifications.mark_all_read(current_user.id)
    await db.commit()

# Tek bir bildirimi okundu durumuna getirir.
@router.put("/{notif_id}/read", status_code=204)
async def mark_one_read(
    notif_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    found = await repos.notifications.mark_read(notif_id, current_user.id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.commit()

# Push bildirim tokenini ekler veya platformunu gunceller.
@router.post("/register-token", response_model=DeviceTokenResponse)
async def register_device_token(
    req: RegisterDeviceTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == current_user.id,
            DeviceToken.token == req.token,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.platform = req.platform
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return existing

    dt = DeviceToken(
        id=str(uuid4()),
        user_id=current_user.id,
        token=req.token,
        platform=req.platform,
    )
    db.add(dt)
    await db.commit()
    await db.refresh(dt)
    return dt

# Mevcut kullaniciya ait push token kaydini siler.
@router.delete("/unregister-token", status_code=204)
async def unregister_device_token(
    req: RegisterDeviceTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        delete(DeviceToken).where(
            DeviceToken.user_id == current_user.id,
            DeviceToken.token == req.token,
        )
    )
    await db.commit()
