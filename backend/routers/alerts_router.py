from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import (
    AlertRespondRequest,
    AlertResponse,
    ClosePostEventRequest,
    PostEventSessionResponse,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])

def _dict_to_alert_response(d: dict) -> AlertResponse:
    recs = d.get("recommendations", [])
    if isinstance(recs, str):
        import json
        try:
            recs = json.loads(recs)
        except Exception:
            recs = []
    return AlertResponse(
        id=d["id"],
        user_id=d["user_id"],
        title=d["title"],
        description=d["description"],
        severity=d["severity"],
        status=d["status"],
        created_at=d["created_at"],
        countdown_total_sec=d["countdown_total_sec"],
        countdown_remaining_sec=d["countdown_remaining_sec"],
        recommendations=recs,
        related_anomaly_id=d.get("related_anomaly_id"),
        resolved_at=d.get("resolved_at"),
    )

@router.get("", response_model=list[AlertResponse])
async def get_my_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="SELF role required")
    alerts = await repos.alerts.list_by_user(current_user.id)
    return [_dict_to_alert_response(a) for a in alerts]

@router.get("/active", response_model=AlertResponse | None)
async def get_active_alert(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="SELF role required")
    alert = await repos.alerts.get_active_by_user(current_user.id)
    return _dict_to_alert_response(alert) if alert else None

@router.get("/{user_id}/for-linked", response_model=list[AlertResponse])
async def get_alerts_for_linked(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    link = await repos.relations.find_active_link(user_id, current_user.id)
    if link is None:
        raise HTTPException(status_code=403, detail="Access denied")
    alerts = await repos.alerts.list_by_user(user_id, limit=30)
    return [_dict_to_alert_response(a) for a in alerts]

@router.put("/{alert_id}/respond", response_model=AlertResponse)
async def respond_to_alert(
    alert_id: str,
    body: AlertRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="Only SELF users can respond to alerts")

    alert = await repos.alerts.get_by_id(alert_id)
    if alert is None or alert["user_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Alert not found")

    if body.action == "OKAY":
        updates = {"status": "acknowledged", "countdown_remaining_sec": 0, "resolved_at": datetime.utcnow()}
        outcome = "acknowledged"
        notif_title = "User Confirmed Safe"
        notif_body = f"Responded 'I'm okay' to {alert['title']}."
    elif body.action == "EMERGENCY":
        updates = {"status": "escalated", "countdown_remaining_sec": 0}
        outcome = "emergency_requested"
        notif_title = "🚨 Emergency Requested"
        notif_body = f"Emergency services requested for {alert['title']}."
    else:
        raise HTTPException(status_code=400, detail="action must be OKAY or EMERGENCY")

    updated = await repos.alerts.update(alert_id, updates)

    await repos.history.create({
        "id": str(uuid4()),
        "user_id": alert["user_id"],
        "item_type": "alert",
        "title": alert["title"],
        "subtitle": alert["description"],
        "severity": alert["severity"],
        "outcome": outcome,
    })

    await repos.notifications.create({
        "id": str(uuid4()),
        "recipient_id": current_user.id,
        "title": notif_title,
        "body": notif_body,
        "notification_type": "alert_response",
        "reference_id": alert_id,
        "reference_type": "alert",
        "is_read": False,
    })

    relations = await repos.relations.find_active_by_self_user(current_user.id)
    for rel in relations:
        await repos.notifications.create({
            "id": str(uuid4()),
            "recipient_id": rel["linked_user_id"],
            "sender_id": current_user.id,
            "title": notif_title,
            "body": f"{current_user.full_name}: {notif_body}",
            "notification_type": "alert_response",
            "reference_id": alert_id,
            "reference_type": "alert",
            "is_read": False,
        })

    await db.commit()
    return _dict_to_alert_response(updated)

@router.post("/{alert_id}/post-event", response_model=PostEventSessionResponse, status_code=201)
async def start_post_event(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    alert = await repos.alerts.get_by_id(alert_id)
    if alert is None or alert["user_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Alert not found")

    await repos.alerts.update(alert_id, {"status": "post_event_monitoring"})

    session_data = {
        "id": str(uuid4()),
        "user_id": current_user.id,
        "alert_id": alert_id,
    }
    session = await repos.post_events.create(session_data)
    await db.commit()
    return session

@router.put("/post-event/{session_id}/close", response_model=PostEventSessionResponse)
async def close_post_event(
    session_id: str,
    body: ClosePostEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    session = await repos.post_events.get_by_id(session_id)
    if session is None or session["user_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    updated_session = await repos.post_events.update(session_id, {
        "ended_at": datetime.utcnow(),
        "outcome": body.outcome,
    })

    alert = await repos.alerts.get_by_id(session["alert_id"])
    if alert:
        await repos.alerts.update(alert["id"], {"status": "resolved", "resolved_at": datetime.utcnow()})
        await repos.history.create({
            "id": str(uuid4()),
            "user_id": alert["user_id"],
            "item_type": "alert",
            "title": alert["title"],
            "subtitle": alert["description"],
            "severity": alert["severity"],
            "outcome": body.outcome,
        })

    await db.commit()
    return updated_session
