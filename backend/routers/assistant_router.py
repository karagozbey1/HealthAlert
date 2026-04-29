from __future__ import annotations

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from services.assistant_service import (
    generate_assistant_summary,
    generate_alert_explanation,
    generate_daily_summary,
)
from services.trend_service import analyze_trends

router = APIRouter(prefix="/assistant", tags=["assistant"])

@router.get("/summary")
async def get_assistant_summary(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    target_id = user_id or current_user.id
    role = current_user.role

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=20)
    alerts = await repos.alerts.list_by_user(target_id, limit=20)
    history = await repos.history.list_by_user(target_id, limit=30)

    return generate_assistant_summary(live, anomalies, alerts, history, role)

@router.get("/alert-explanation/{alert_id}")
async def get_alert_explanation(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    alert = await repos.alerts.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")

    if alert["user_id"] != current_user.id:
        link = await repos.relations.find_active_link(alert["user_id"], current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(alert["user_id"])
    return generate_alert_explanation(alert, live)

@router.get("/daily-summary")
async def get_daily_summary(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    target_id = user_id or current_user.id
    role = current_user.role

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=50)
    alerts = await repos.alerts.list_by_user(target_id, limit=50)

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=24)
    anomalies_24h = [a for a in anomalies if _parse_dt(a) >= cutoff]
    alerts_24h = [a for a in alerts if _parse_dt(a) >= cutoff]

    return generate_daily_summary(live, anomalies_24h, alerts_24h, role)

@router.get("/trends")
async def get_trends(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    target_id = user_id or current_user.id

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=50)
    history = await repos.history.list_by_user(target_id, limit=50)

    return analyze_trends(history, anomalies, live, current_user.role)

def _parse_dt(item: dict) -> datetime:
    for key in ("detected_at", "created_at", "timestamp"):
        val = item.get(key)
        if val is not None:
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", ""))
            except (ValueError, TypeError):
                continue
    return datetime.min
