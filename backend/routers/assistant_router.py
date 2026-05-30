from __future__ import annotations

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import AssistantAckRequest, AssistantAckResponse, AssistantStateResponse, AssistantActionResponse, AssistantSummaryResponse
from services.assistant_service import (
    generate_assistant_summary,
    generate_alert_explanation,
    generate_daily_summary,
)
from services.care_assistant_service import care_assistant_service
from services.trend_service import analyze_trends

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Asistan ozetini rol ve bagli kullanici baglamiyla uretir.
@router.get("/summary")
async def get_assistant_summary(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
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

# Tek bir alert icin aciklama metni uretir.
@router.get("/alert-explanation/{alert_id}")
async def get_alert_explanation(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
    alert = await repos.alerts.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")

    if alert["user_id"] != current_user.id:
        link = await repos.relations.find_active_link(alert["user_id"], current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(alert["user_id"])
    return generate_alert_explanation(alert, live)

# Son 24 saatin gunluk ozetini hedef kullanici icin uretir.
@router.get("/daily-summary")
async def get_daily_summary(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
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

# Canli durum, anomaly ve history kaydindan trend cikartir.
@router.get("/trends")
async def get_trends(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
    target_id = user_id or current_user.id

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=50)
    history = await repos.history.list_by_user(target_id, limit=50)

    return analyze_trends(history, anomalies, live, current_user.role)

# Tarih alanlarindan ilk gecerli datetime degerini bulur.
def _parse_dt(item: dict) -> datetime:
    """Asistan endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
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


# Kullanici icin mevcut asistan durumunu dondurur.
@router.get("/state/{user_id}", response_model=AssistantStateResponse)
async def get_assistant_state(
    user_id: str,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
    if user_id != current_user.id:
        link = await repos.relations.find_active_link(user_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    if repos.assistant is None:
        raise HTTPException(status_code=503, detail="Assistant repo not available")

    state = await repos.assistant.get_or_create_state(user_id)
    return state


# Kullaniciya ait aktif asistan aksiyonlarini listeler.
@router.get("/actions/{user_id}", response_model=list[AssistantActionResponse])
async def get_assistant_actions(
    user_id: str,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
    if user_id != current_user.id:
        link = await repos.relations.find_active_link(user_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    if repos.assistant is None:
        return []

    return await repos.assistant.list_active_actions(user_id)


# Kritik onay cevabini kaydedip asistani yeni moda tasir.
@router.post("/ack", response_model=AssistantAckResponse)
async def post_assistant_ack(
    body: AssistantAckRequest,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Asistan güncelleme isteğini doğrulayıp uygular."""
    if body.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Erişim izni yok")

    result = await care_assistant_service.handle_user_ack(
        repos=repos,
        user_id=body.user_id,
        response=body.response,
        note=body.note,
        action_id=body.action_id,
    )
    return result


# Suresi dolan kritik onay beklemelerini topluca isler.
@router.post("/check-timeouts")
async def check_assistant_timeouts(
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Asistan endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    if repos.assistant is None:
        return {"processed": 0}

    from datetime import datetime as _dt
    due = await repos.assistant.get_due_ack_timeouts(_dt.utcnow())
    results = []
    for state in due:
        r = await care_assistant_service.handle_critical_timeout(repos, state["user_id"])
        results.append(r)
    return {"processed": len(results), "results": results}


# Kullanici icin bakim asistani ozetini dondurur.
@router.get("/care-summary/{user_id}", response_model=AssistantSummaryResponse)
async def get_care_summary(
    user_id: str,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için asistan okuma isteğini işler."""
    if user_id != current_user.id:
        link = await repos.relations.find_active_link(user_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erişim izni yok")

    return await care_assistant_service.get_current_assistant_summary(repos, user_id)
