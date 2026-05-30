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
    HelpRequestResponse,
    PostEventSessionResponse,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Ham alert sozlugunu API semasina donusturur.
def _dict_to_alert_response(d: dict) -> AlertResponse:
    """Alarm endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
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

# SELF kullanicisinin kendi alert listesini dondurur.
# DOCTOR/RELATIVE icin yetkili hasta alertlerini dondurur.
@router.get("", response_model=list[AlertResponse])
async def get_my_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için alarm okuma isteğini işler."""
    if current_user.role == "SELF":
        alerts = await repos.alerts.list_by_user(current_user.id)
        return [_dict_to_alert_response(a) for a in alerts]

    # DOCTOR / RELATIVE: return alerts for all linked patients
    relations = await repos.relations.find_active_by_linked_user(current_user.id)
    result = []
    seen: set[str] = set()
    for rel in relations:
        pid = rel["self_user_id"]
        if pid in seen:
            continue
        seen.add(pid)
        patient_alerts = await repos.alerts.list_by_user(pid, limit=20)
        result.extend(patient_alerts)
    result.sort(key=lambda a: a.get("created_at", datetime.utcfromtimestamp(0)), reverse=True)
    return [_dict_to_alert_response(a) for a in result[:50]]

# SELF kullanicisinin aktif alert kaydini dondurur.
@router.get("/active", response_model=AlertResponse | None)
async def get_active_alert(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için alarm okuma isteğini işler."""
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="SELF role required")
    alert = await repos.alerts.get_active_by_user(current_user.id)
    return _dict_to_alert_response(alert) if alert else None

# Yetkili bagli kullanicilar icin hedef kisinin alertlerini listeler.
@router.get("/{user_id}/for-linked", response_model=list[AlertResponse])
async def get_alerts_for_linked(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için alarm okuma isteğini işler."""
    link = await repos.relations.find_active_link(user_id, current_user.id)
    if link is None:
        raise HTTPException(status_code=403, detail="Access denied")
    alerts = await repos.alerts.list_by_user(user_id, limit=30)
    return [_dict_to_alert_response(a) for a in alerts]

# Kullanici yanitina gore alert durumunu gunceller ve bildirim uretir.
@router.put("/{alert_id}/respond", response_model=AlertResponse)
async def respond_to_alert(
    alert_id: str,
    body: AlertRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm güncelleme isteğini doğrulayıp uygular."""
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

# Alert icin post-event izleme oturumu baslatir.
@router.post("/{alert_id}/post-event", response_model=PostEventSessionResponse, status_code=201)
async def start_post_event(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
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

# Post-event oturumunu kapatip alerti cozulmus sayar.
@router.put("/post-event/{session_id}/close", response_model=PostEventSessionResponse)
async def close_post_event(
    session_id: str,
    body: ClosePostEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm silme veya kapatma isteğini doğrulayıp uygular."""
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


# Hasta yardim cagrisini olusturur ve baglantilarini bilgilendirir.
@router.post("/help", response_model=HelpRequestResponse, status_code=201)
async def request_help(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="Only SELF users can request help")

    alert_id = str(uuid4())
    live = await repos.live_status.get_by_user(current_user.id)

    recs = [
        "Güvenli bir yerde olduğunuzdan emin olun.",
        "Doktorunuz veya yakınınız bilgilendirildi.",
        "Acil durumda 112'yi arayın.",
    ]

    alert_data = {
        "id": alert_id,
        "user_id": current_user.id,
        "title": "Yardım Çağrısı",
        "description": f"{current_user.full_name} yardım istedi.",
        "severity": "critical",
        "status": "active",
        "countdown_total_sec": 300,
        "countdown_remaining_sec": 300,
        "recommendations": recs,
    }
    alert = await repos.alerts.create(alert_data)

    await repos.history.create({
        "id": str(uuid4()),
        "user_id": current_user.id,
        "item_type": "alert",
        "title": "Yardım Çağrısı",
        "subtitle": "Manuel yardım çağrısı gönderildi.",
        "severity": "critical",
        "outcome": "help_requested",
    })

    # Fan-out to all linked doctors and relatives
    relations = await repos.relations.find_active_by_self_user(current_user.id)
    notified: list[str] = []
    for rel in relations:
        linked_id = rel["linked_user_id"]
        await repos.notifications.create({
            "id": str(uuid4()),
            "recipient_id": linked_id,
            "sender_id": current_user.id,
            "title": "🚨 Yardım Çağrısı",
            "body": f"{current_user.full_name} yardım istedi. Lütfen kontrol edin.",
            "notification_type": "help_request",
            "reference_id": alert_id,
            "reference_type": "alert",
            "is_read": False,
        })
        notified.append(linked_id)

    await db.commit()
    return HelpRequestResponse(
        alert_id=alert_id,
        notified_count=len(notified),
        message="Yardım çağrısı gönderildi.",
    )


# Doktor veya yakın alerti goruldu olarak isaretler.
@router.post("/{alert_id}/ack", status_code=200)
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    if current_user.role not in ("DOCTOR", "RELATIVE"):
        raise HTTPException(status_code=403, detail="Only DOCTOR or RELATIVE can acknowledge alerts")

    alert = await repos.alerts.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    # ACL: check that the current user is linked to the patient
    link = await repos.relations.find_active_link(alert["user_id"], current_user.id)
    if link is None:
        raise HTTPException(status_code=403, detail="Access denied")

    await repos.alerts.update(alert_id, {
        "status": "acknowledged",
        "resolved_at": datetime.utcnow(),
    })

    await repos.notifications.create({
        "id": str(uuid4()),
        "recipient_id": alert["user_id"],
        "sender_id": current_user.id,
        "title": "Uyarı Görüldü",
        "body": f"{current_user.full_name} uyarınızı gördü.",
        "notification_type": "alert_ack",
        "reference_id": alert_id,
        "reference_type": "alert",
        "is_read": False,
    })

    await db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


# Hasta canli durumunu anomali kurallariyla degerlendirir.
@router.post("/evaluate", status_code=201)
async def evaluate_live_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Alarm endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="SELF role required")

    live = await repos.live_status.get_by_user(current_user.id)
    if live is None:
        return {"evaluated": False, "reason": "no_live_data"}

    alerts_created: list[str] = []

    hr = live.get("heart_rate", 0)
    spo2 = live.get("spo2", 100)
    risk = live.get("risk_score", 0)
    hr_valid = live.get("hr_valid", True)
    spo2_valid = live.get("spo2_valid", True)
    signal_quality = live.get("signal_quality", 1.0) or 1.0

    # Only evaluate if signal is usable
    if signal_quality < 0.2:
        return {"evaluated": False, "reason": "signal_quality_too_low"}

    existing = await repos.alerts.get_active_by_user(current_user.id)
    if existing:
        return {"evaluated": True, "reason": "active_alert_exists", "alerts_created": []}

    alert_type = None
    title = None
    description = None
    severity = "medium"

    if risk >= 0.7:
        alert_type = "high_risk"
        title = "Yüksek Risk Algılandı"
        description = "Risk skoru kritik seviyeye ulaştı."
        severity = "critical"
    elif spo2_valid and spo2 < 90:
        alert_type = "low_spo2_est"
        title = "Düşük Oksijen Tahmini"
        description = f"SpO2 tahmini %{spo2:.1f} — düşük."
        severity = "high"
    elif hr_valid and (hr > 130 or hr < 45):
        alert_type = "abnormal_heart_rate"
        title = "Anormal Kalp Atışı"
        description = f"Kalp atışı {hr:.0f} BPM — olağandışı."
        severity = "high"

    if alert_type:
        aid = str(uuid4())
        await repos.alerts.create({
            "id": aid,
            "user_id": current_user.id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": "active",
            "countdown_total_sec": 300,
            "countdown_remaining_sec": 300,
            "recommendations": ["Durumunuzu değerlendirin.", "Gerekirse yardım çağırın."],
        })
        # Fan-out notifications
        relations = await repos.relations.find_active_by_self_user(current_user.id)
        for rel in relations:
            await repos.notifications.create({
                "id": str(uuid4()),
                "recipient_id": rel["linked_user_id"],
                "sender_id": current_user.id,
                "title": f"⚠️ {title}",
                "body": f"{current_user.full_name}: {description}",
                "notification_type": "anomaly_alert",
                "reference_id": aid,
                "reference_type": "alert",
                "is_read": False,
            })
        alerts_created.append(aid)
        await db.commit()

    return {"evaluated": True, "alerts_created": alerts_created}
