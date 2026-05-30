from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from services.chat_service import (
    get_context_preview,
    get_suggestions,
    process_chat_message,
)
from services.llm_client import get_llm_client

router = APIRouter(prefix="/assistant", tags=["assistant-chat"])

class ChatRequest(BaseModel):
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    screen_context: str = ""
    target_user_id: Optional[str] = None

class UIActionOut(BaseModel):
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    label: str
    route: str

class ChatResponse(BaseModel):
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    session_id: str
    message: str
    source: str
    disclaimer: str
    ui_actions: List[UIActionOut] = []
    context_summary: str = ""

class SuggestionsResponse(BaseModel):
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    suggestions: List[str]

class ChatStatusResponse(BaseModel):
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    llm_configured: bool
    llm_model: str
    llm_status: str
    fallback_available: bool = True

# Sohbet istegini isleyip ilgili kullanici baglamiyla asistan yanitini dondurur.
@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Sohbet endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    role = current_user.role
    target_id = body.target_user_id or current_user.id

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erisim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=20)
    alerts = await repos.alerts.list_by_user(target_id, limit=20)
    history = await repos.history.list_by_user(target_id, limit=30)

    clinical_notes = None
    if role == "DOCTOR":
        try:
            clinical_notes = await repos.clinical_notes.list_by_user(target_id, limit=5)
        except Exception:
            clinical_notes = None

    patient_name = ""
    if target_id != current_user.id:
        try:
            from sqlalchemy import select
            from models import User as UserModel
            result = await db.execute(select(UserModel).where(UserModel.id == target_id))
            target_user = result.scalar_one_or_none()
            if target_user:
                patient_name = target_user.full_name
        except Exception:
            pass

    is_demo = settings.APP_MODE == "demo"

    result = await process_chat_message(
        message=body.message,
        session_id=body.session_id,
        user_id=current_user.id,
        target_user_id=target_id,
        role=role,
        user_name=current_user.full_name,
        patient_name=patient_name,
        screen_context=body.screen_context,
        live_status=live,
        recent_alerts=alerts,
        recent_anomalies=anomalies,
        recent_history=history,
        clinical_notes=clinical_notes,
        is_demo_mode=is_demo,
    )

    return ChatResponse(**result)

# Oturum baslatmak icin role uygun hazir soru onerilerini dondurur.
@router.get("/suggestions", response_model=SuggestionsResponse)
async def suggestions(
    current_user: User = Depends(get_current_user),
):
    """Sohbet endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    return SuggestionsResponse(suggestions=get_suggestions(current_user.role))

# Secilen kullanici icin asistanin gorecegi baglam metnini onizleme olarak uretir.
@router.get("/context-preview")
async def context_preview(
    target_user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Sohbet endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    target_id = target_user_id or current_user.id
    role = current_user.role

    if target_id != current_user.id:
        link = await repos.relations.find_active_link(target_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Erisim izni yok")

    live = await repos.live_status.get_by_user(target_id)
    anomalies = await repos.anomalies.list_by_user(target_id, limit=20)
    alerts = await repos.alerts.list_by_user(target_id, limit=20)
    history = await repos.history.list_by_user(target_id, limit=30)

    clinical_notes = None
    if role == "DOCTOR":
        try:
            clinical_notes = await repos.clinical_notes.list_by_user(target_id, limit=5)
        except Exception:
            pass

    is_demo = settings.APP_MODE == "demo"

    text = get_context_preview(
        role=role,
        user_name=current_user.full_name,
        live_status=live,
        recent_alerts=alerts,
        recent_anomalies=anomalies,
        recent_history=history,
        clinical_notes=clinical_notes,
        is_demo_mode=is_demo,
    )
    return {"context": text}

# LLM baglantisinin ve yerel yedek akisin kullanilabilirlik durumunu raporlar.
@router.get("/chat-status", response_model=ChatStatusResponse)
async def chat_status(
    current_user: User = Depends(get_current_user),
):
    """Sohbet endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    llm = get_llm_client()
    status_info = await llm.health_check()
    return ChatStatusResponse(
        llm_configured=llm.is_configured,
        llm_model=llm.model,
        llm_status=status_info.get("status", "unknown"),
        fallback_available=True,
    )
