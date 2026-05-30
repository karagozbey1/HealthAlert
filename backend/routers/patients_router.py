"""
patients_router.py
------------------
Role-based patient data access endpoints.

Access rules:
  - SELF   : can only access own data (patient_id == user.id)
  - DOCTOR : can access patients linked via UserRelation (self_user_id=patient, linked_user_id=doctor)
  - RELATIVE: same link model as DOCTOR
  - Unauthorized → 403

New endpoints (do not replace existing /live/{user_id}):
  GET /patients/accessible          → list of patients the caller can see
  GET /patients/{patient_id}/live   → latest live status (403 if not authorized)
  GET /patients/{patient_id}/summary → compact summary card
  GET /doctor/patients              → doctor-only shortcut (same as accessible)
  GET /relative/patients            → relative-only shortcut (same as accessible)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import LiveStatusResponse, PatientSummaryResponse, UserResponse

router = APIRouter(tags=["patients"])

# ──────────────────────────────────────────
# Access helper
# ──────────────────────────────────────────

async def can_access_patient(user: User, patient_id: str, repos: RepoSet) -> bool:
    """Kullanıcının seçili hastanın sağlık verisini okuyup okuyamayacağını kontrol eder."""
    # SELF can only see themselves.
    if user.role == "SELF":
        return user.id == patient_id
    # DOCTOR / RELATIVE need an active UserRelation where patient is the self_user.
    link = await repos.relations.find_active_link(patient_id, user.id)
    return link is not None


def _risk_level(score: float) -> str:
    """Sayısal risk skorunu mobil arayüzde kullanılan risk seviyesine çevirir."""
    if score >= 0.7:
        return "critical"
    if score >= 0.5:
        return "warning"
    if score >= 0.3:
        return "watch"
    return "normal"


# ──────────────────────────────────────────
# /patients/accessible
# ──────────────────────────────────────────

@router.get("/patients/accessible", response_model=list[UserResponse])
async def get_accessible_patients(
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Mevcut kullanıcının erişebildiği hasta listesini döndürür."""
    if current_user.role == "SELF":
        user = await repos.users.get_by_id(current_user.id)
        return [user] if user else []

    relations = await repos.relations.find_active_by_linked_user(current_user.id)
    patients: list[dict] = []
    seen: set[str] = set()
    for rel in relations:
        pid = rel["self_user_id"]
        if pid in seen:
            continue
        seen.add(pid)
        user = await repos.users.get_by_id(pid)
        if user:
            patients.append(user)
    return patients


# ──────────────────────────────────────────
# /patients/{patient_id}/live
# ──────────────────────────────────────────

@router.get("/patients/{patient_id}/live", response_model=LiveStatusResponse)
async def get_patient_live(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcının seçili hastanın en güncel canlı durumunu okumasını sağlar."""
    if not await can_access_patient(current_user, patient_id, repos):
        raise HTTPException(status_code=403, detail="Access denied")

    live = await repos.live_status.get_by_user(patient_id)
    if live is None:
        raise HTTPException(status_code=404, detail="No live data yet for this patient")
    return live


# ──────────────────────────────────────────
# /patients/{patient_id}/summary
# ──────────────────────────────────────────

@router.get("/patients/{patient_id}/summary", response_model=PatientSummaryResponse)
async def get_patient_summary(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için hasta özet kartı verisini hazırlar."""
    if not await can_access_patient(current_user, patient_id, repos):
        raise HTTPException(status_code=403, detail="Access denied")

    patient = await repos.users.get_by_id(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    live = await repos.live_status.get_by_user(patient_id)

    if live is None:
        return PatientSummaryResponse(
            patient_id=patient_id,
            display_name=patient["full_name"],
            email=patient["email"],
            role=patient["role"],
            has_live_data=False,
        )

    ts: Optional[datetime] = live.get("timestamp")
    last_seen: Optional[int] = None
    if ts is not None:
        delta = datetime.utcnow() - ts
        last_seen = int(delta.total_seconds())

    risk = float(live.get("risk_score") or 0.0)

    return PatientSummaryResponse(
        patient_id=patient_id,
        display_name=patient["full_name"],
        email=patient["email"],
        role=patient["role"],
        has_live_data=True,
        latest_timestamp=ts,
        heart_rate=live.get("heart_rate"),
        heart_rate_valid=live.get("hr_valid"),
        spo2=live.get("spo2"),
        spo2_valid=live.get("spo2_valid"),
        movement_percent=live.get("motion_score"),
        risk_score=risk,
        risk_level=_risk_level(risk),
        signal_quality=live.get("signal_quality"),
        last_seen_seconds=last_seen,
        finger_present=live.get("finger_present"),
        source=live.get("source"),
    )


# ──────────────────────────────────────────
# /doctor/patients  (doctor role only)
# ──────────────────────────────────────────

@router.get("/doctor/patients", response_model=list[UserResponse])
async def get_doctor_patients(
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Doktor rolündeki kullanıcının atanmış hasta listesini döndürür."""
    if current_user.role != "DOCTOR":
        raise HTTPException(status_code=403, detail="Doctor role required")

    relations = await repos.relations.find_active_by_linked_user(current_user.id)
    patients: list[dict] = []
    seen: set[str] = set()
    for rel in relations:
        pid = rel["self_user_id"]
        if pid in seen:
            continue
        seen.add(pid)
        user = await repos.users.get_by_id(pid)
        if user:
            patients.append(user)
    return patients


# ──────────────────────────────────────────
# /relative/patients  (relative role only)
# ──────────────────────────────────────────

@router.get("/relative/patients", response_model=list[UserResponse])
async def get_relative_patients(
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yakın rolündeki kullanıcının izlediği hasta listesini döndürür."""
    if current_user.role != "RELATIVE":
        raise HTTPException(status_code=403, detail="Relative role required")

    relations = await repos.relations.find_active_by_linked_user(current_user.id)
    patients: list[dict] = []
    seen: set[str] = set()
    for rel in relations:
        pid = rel["self_user_id"]
        if pid in seen:
            continue
        seen.add(pid)
        user = await repos.users.get_by_id(pid)
        if user:
            patients.append(user)
    return patients
