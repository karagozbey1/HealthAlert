# SQLite repository siniflari mevcut ORM erisimini ortak bir katmanda toplar.
# Her sinif AsyncSession uzerinden onceki router mantigini koruyarak calisir.
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    AlertEvent,
    AnomalyEvent,
    AppSettings,
    AssistantAcknowledgement,
    AssistantAction,
    AssistantState,
    ClinicalNote,
    DevicePacketLog,
    DeviceRegistration,
    HistoryItem,
    LearningCaptureSession,
    LearningWindow,
    LinkCode,
    LiveStatus,
    ModelWindowLog,
    ModelVersionRegistry,
    NotificationItem,
    PersonalHealthProfile,
    PersonalRiskMemory,
    PersonalTrendSnapshot,
    PostEventSession,
    SimulationState,
    User,
    UserBaseline,
    UserFeedbackEvent,
    UserRelation,
)
from repositories.base import (
    AbstractAlertRepo,
    AbstractAnomalyRepo,
    AbstractBaselineRepo,
    AbstractClinicalNoteRepo,
    AbstractDeviceRepo,
    AbstractHistoryRepo,
    AbstractLearningRepo,
    AbstractLinkCodeRepo,
    AbstractLiveStatusRepo,
    AbstractNotificationRepo,
    AbstractPersonalizationRepo,
    AbstractPostEventRepo,
    AbstractRelationRepo,
    AbstractSettingsRepo,
    AbstractSimulationStateRepo,
    AbstractUserRepo,
    AbstractAssistantRepo,
)


# User ORM nesnesini API dostu bir dict yapisina cevirir.
def _user_to_dict(u: User) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": u.id, "email": u.email, "password_hash": u.password_hash,
        "role": u.role, "full_name": u.full_name, "phone": u.phone,
        "birth_date": u.birth_date, "created_at": u.created_at,
    }


# LinkCode ORM nesnesini tasinabilir bir dict yapisina cevirir.
def _code_to_dict(c: LinkCode) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": c.id, "code": c.code, "owner_id": c.owner_id,
        "code_type": c.code_type, "is_active": c.is_active,
        "uses_remaining": c.uses_remaining, "expires_at": c.expires_at,
        "created_at": c.created_at,
    }


def _rel_to_dict(r: UserRelation) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": r.id, "self_user_id": r.self_user_id,
        "linked_user_id": r.linked_user_id, "relation_type": r.relation_type,
        "is_active": r.is_active, "created_at": r.created_at,
        "revoked_at": r.revoked_at,
    }


def _live_to_dict(ls: LiveStatus) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": ls.id, "user_id": ls.user_id, "heart_rate": ls.heart_rate,
        "spo2": ls.spo2, "motion_score": ls.motion_score,
        "risk_score": ls.risk_score, "scenario": ls.scenario,
        "timestamp": ls.timestamp,
        "final_risk_score": ls.risk_score,
        "personalized_risk_score": None,
        "ml_evidence_score": None,
        "ml_adjustment": None,
        "fusion_applied": None,
        "model_window_status": None,
        "ml_base_score": None,
        "personal_adjustment": None,
        "fusion_mode": None,
        "model_version": None,
        "ml_confidence": None,
    }


def _anomaly_to_dict(a: AnomalyEvent) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": a.id, "user_id": a.user_id, "metric": a.metric,
        "value": a.value, "unit": a.unit, "severity": a.severity,
        "detected_at": a.detected_at, "summary": a.summary,
    }


def _alert_to_dict(a: AlertEvent) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": a.id, "user_id": a.user_id, "title": a.title,
        "description": a.description, "severity": a.severity,
        "status": a.status, "created_at": a.created_at,
        "countdown_total_sec": a.countdown_total_sec,
        "countdown_remaining_sec": a.countdown_remaining_sec,
        "recommendations": a.get_recommendations(),
        "related_anomaly_id": a.related_anomaly_id,
        "resolved_at": a.resolved_at,
    }


def _post_event_to_dict(s: PostEventSession) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": s.id, "user_id": s.user_id, "alert_id": s.alert_id,
        "started_at": s.started_at, "ended_at": s.ended_at,
        "outcome": s.outcome,
    }


def _history_to_dict(h: HistoryItem) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": h.id, "user_id": h.user_id, "item_type": h.item_type,
        "title": h.title, "subtitle": h.subtitle, "timestamp": h.timestamp,
        "severity": h.severity, "outcome": h.outcome,
    }


def _notif_to_dict(n: NotificationItem) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": n.id, "recipient_id": n.recipient_id, "sender_id": n.sender_id,
        "title": n.title, "body": n.body, "notification_type": n.notification_type,
        "reference_id": n.reference_id, "reference_type": n.reference_type,
        "is_read": n.is_read, "created_at": n.created_at,
    }


def _note_to_dict(n: ClinicalNote) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": n.id, "doctor_id": n.doctor_id, "patient_id": n.patient_id,
        "note": n.note, "recommendation": n.recommendation,
        "created_at": n.created_at, "updated_at": n.updated_at,
    }


def _settings_to_dict(s: AppSettings) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "user_id": s.user_id,
        "notifications_enabled": s.notifications_enabled,
        "battery_mode": s.battery_mode,
        "background_monitoring": s.background_monitoring,
        "update_interval_seconds": s.update_interval_seconds,
        "alert_sensitivity": getattr(s, "alert_sensitivity", "normal"),
    }


def _sim_to_dict(s: SimulationState) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "user_id": s.user_id,
        "scenario_index": s.scenario_index,
        "tick_count": s.tick_count,
        "last_updated": s.last_updated,
    }


# ===================================================================
# User
# ===================================================================

class SqliteUserRepo(AbstractUserRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(User).where(User.id == user_id))
        u = r.scalar_one_or_none()
        return _user_to_dict(u) if u else None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(User).where(User.email == email))
        u = r.scalar_one_or_none()
        return _user_to_dict(u) if u else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        u = User(**data)
        self.db.add(u)
        await self.db.flush()
        await self.db.refresh(u)
        return _user_to_dict(u)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(User).where(User.id == user_id))
        u = r.scalar_one_or_none()
        if u is None:
            return None
        for k, v in data.items():
            setattr(u, k, v)
        self.db.add(u)
        await self.db.flush()
        await self.db.refresh(u)
        return _user_to_dict(u)

    async def list_by_role(self, role: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(User).where(User.role == role))
        return [_user_to_dict(u) for u in r.scalars().all()]


# ===================================================================
# Link codes
# ===================================================================

class SqliteLinkCodeRepo(AbstractLinkCodeRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_id(self, code_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(LinkCode).where(LinkCode.id == code_id))
        c = r.scalar_one_or_none()
        return _code_to_dict(c) if c else None

    async def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(LinkCode).where(LinkCode.code == code))
        c = r.scalar_one_or_none()
        return _code_to_dict(c) if c else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        c = LinkCode(**data)
        self.db.add(c)
        await self.db.flush()
        await self.db.refresh(c)
        return _code_to_dict(c)

    async def update(self, code_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(LinkCode).where(LinkCode.id == code_id))
        c = r.scalar_one_or_none()
        if c is None:
            return None
        for k, v in data.items():
            setattr(c, k, v)
        self.db.add(c)
        await self.db.flush()
        await self.db.refresh(c)
        return _code_to_dict(c)

    async def list_by_owner(self, owner_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(LinkCode).where(LinkCode.owner_id == owner_id)
            .order_by(LinkCode.created_at.desc())
        )
        return [_code_to_dict(c) for c in r.scalars().all()]


# ===================================================================
# Relations
# ===================================================================

class SqliteRelationRepo(AbstractRelationRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_id(self, relation_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(UserRelation).where(UserRelation.id == relation_id))
        rel = r.scalar_one_or_none()
        return _rel_to_dict(rel) if rel else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        rel = UserRelation(**data)
        self.db.add(rel)
        await self.db.flush()
        await self.db.refresh(rel)
        return _rel_to_dict(rel)

    async def update(self, relation_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(UserRelation).where(UserRelation.id == relation_id))
        rel = r.scalar_one_or_none()
        if rel is None:
            return None
        for k, v in data.items():
            setattr(rel, k, v)
        self.db.add(rel)
        await self.db.flush()
        await self.db.refresh(rel)
        return _rel_to_dict(rel)

    async def find_active_by_self_user(self, self_user_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserRelation).where(
                UserRelation.self_user_id == self_user_id,
                UserRelation.is_active == True,  # noqa: E712
            )
        )
        return [_rel_to_dict(rel) for rel in r.scalars().all()]

    async def find_active_by_linked_user(self, linked_user_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserRelation).where(
                UserRelation.linked_user_id == linked_user_id,
                UserRelation.is_active == True,  # noqa: E712
            )
        )
        return [_rel_to_dict(rel) for rel in r.scalars().all()]

    async def find_active_link(self, self_user_id: str, linked_user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserRelation).where(
                UserRelation.self_user_id == self_user_id,
                UserRelation.linked_user_id == linked_user_id,
                UserRelation.is_active == True,  # noqa: E712
            )
        )
        rel = r.scalar_one_or_none()
        return _rel_to_dict(rel) if rel else None


# ===================================================================
# Live status
# ===================================================================

class SqliteLiveStatusRepo(AbstractLiveStatusRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(LiveStatus).where(LiveStatus.user_id == user_id))
        ls = r.scalar_one_or_none()
        if ls is None:
            return None

        live = _live_to_dict(ls)

        # Enrich with latest DevicePacketLog BLE/sensor quality fields.
        pkt_result = await self.db.execute(
            select(DevicePacketLog)
            .where(DevicePacketLog.user_id == user_id)
            .order_by(DevicePacketLog.ingested_at.desc())
            .limit(1)
        )
        latest_pkt = pkt_result.scalars().first()
        if latest_pkt is not None:
            live["signal_quality"] = latest_pkt.signal_quality
            live["hr_valid"] = latest_pkt.hr_valid
            live["spo2_valid"] = latest_pkt.spo2_valid
            live["finger_present"] = latest_pkt.finger_detected
            live["source"] = "ble_live" if latest_pkt.mode == "real" else "mock"

        log_result = await self.db.execute(
            select(ModelWindowLog)
            .where(ModelWindowLog.user_id == user_id)
            .order_by(ModelWindowLog.created_at.desc())
            .limit(1)
        )
        latest_log = log_result.scalars().first()
        if latest_log is not None:
            live.update(
                {
                    "final_risk_score": ls.risk_score,
                    "personalized_risk_score": latest_log.personalized_risk_score,
                    "ml_evidence_score": latest_log.ml_evidence_score,
                    "ml_adjustment": latest_log.personal_adjustment,
                    "fusion_applied": latest_log.ml_base_score is not None,
                    "model_window_status": {
                        "model_ready": latest_log.model_ready,
                        "sample_rate_hz": latest_log.sample_rate_hz,
                        "sample_count": latest_log.sample_count,
                        "fusion_mode": latest_log.fusion_mode,
                    },
                    "ml_base_score": latest_log.ml_base_score,
                    "personal_adjustment": latest_log.personal_adjustment,
                    "fusion_mode": latest_log.fusion_mode,
                    "model_version": latest_log.model_version,
                    "ml_confidence": latest_log.ml_confidence,
                }
            )
        else:
            live.update(
                {
                    "final_risk_score": ls.risk_score,
                    "personalized_risk_score": ls.risk_score,
                    "fusion_mode": "fallback_personalization_only",
                    "fusion_applied": False,
                }
            )

        return live

    async def upsert(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(LiveStatus).where(LiveStatus.user_id == user_id))
        ls = r.scalar_one_or_none()
        if ls is None:
            ls = LiveStatus(id=str(uuid4()), user_id=user_id, **data)
            self.db.add(ls)
        else:
            for k, v in data.items():
                setattr(ls, k, v)
        await self.db.flush()
        await self.db.refresh(ls)
        return _live_to_dict(ls)


# ===================================================================
# Anomaly events
# ===================================================================

class SqliteAnomalyRepo(AbstractAnomalyRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        a = AnomalyEvent(**data)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _anomaly_to_dict(a)

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AnomalyEvent)
            .where(AnomalyEvent.user_id == user_id)
            .order_by(AnomalyEvent.detected_at.desc())
            .limit(limit)
        )
        return [_anomaly_to_dict(a) for a in r.scalars().all()]


# ===================================================================
# Alert events
# ===================================================================

class SqliteAlertRepo(AbstractAlertRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
        a = r.scalar_one_or_none()
        return _alert_to_dict(a) if a else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        recommendations = data.pop("recommendations", [])
        a = AlertEvent(**data)
        if recommendations:
            a.set_recommendations(recommendations)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _alert_to_dict(a)

    async def update(self, alert_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
        a = r.scalar_one_or_none()
        if a is None:
            return None
        recommendations = data.pop("recommendations", None)
        for k, v in data.items():
            setattr(a, k, v)
        if recommendations is not None:
            a.set_recommendations(recommendations)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _alert_to_dict(a)

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AlertEvent)
            .where(AlertEvent.user_id == user_id)
            .order_by(AlertEvent.created_at.desc())
            .limit(limit)
        )
        return [_alert_to_dict(a) for a in r.scalars().all()]

    async def get_active_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AlertEvent)
            .where(
                AlertEvent.user_id == user_id,
                AlertEvent.status.notin_(["resolved", "acknowledged"]),
            )
            .order_by(AlertEvent.created_at.desc())
        )
        a = r.scalars().first()
        return _alert_to_dict(a) if a else None

    async def get_countdown_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AlertEvent).where(
                AlertEvent.user_id == user_id,
                AlertEvent.status == "countdown",
            )
        )
        return [_alert_to_dict(a) for a in r.scalars().all()]


# ===================================================================
# Post-event sessions
# ===================================================================

class SqlitePostEventRepo(AbstractPostEventRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(PostEventSession).where(PostEventSession.id == session_id))
        s = r.scalar_one_or_none()
        return _post_event_to_dict(s) if s else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        s = PostEventSession(**data)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _post_event_to_dict(s)

    async def update(self, session_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(PostEventSession).where(PostEventSession.id == session_id))
        s = r.scalar_one_or_none()
        if s is None:
            return None
        for k, v in data.items():
            setattr(s, k, v)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _post_event_to_dict(s)


# ===================================================================
# History items
# ===================================================================

class SqliteHistoryRepo(AbstractHistoryRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        h = HistoryItem(**data)
        self.db.add(h)
        await self.db.flush()
        await self.db.refresh(h)
        return _history_to_dict(h)

    async def list_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(HistoryItem)
            .where(HistoryItem.user_id == user_id)
            .order_by(HistoryItem.timestamp.desc())
            .limit(limit)
        )
        return [_history_to_dict(h) for h in r.scalars().all()]


# ===================================================================
# Notifications
# ===================================================================

class SqliteNotificationRepo(AbstractNotificationRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        n = NotificationItem(**data)
        self.db.add(n)
        await self.db.flush()
        await self.db.refresh(n)
        return _notif_to_dict(n)

    async def list_by_recipient(self, recipient_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(NotificationItem)
            .where(NotificationItem.recipient_id == recipient_id)
            .order_by(NotificationItem.created_at.desc())
            .limit(limit)
        )
        return [_notif_to_dict(n) for n in r.scalars().all()]

    async def mark_read(self, notif_id: str, recipient_id: str) -> bool:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(NotificationItem).where(
                NotificationItem.id == notif_id,
                NotificationItem.recipient_id == recipient_id,
            )
        )
        n = r.scalar_one_or_none()
        if n is None:
            return False
        n.is_read = True
        self.db.add(n)
        await self.db.flush()
        return True

    async def mark_all_read(self, recipient_id: str) -> int:
        """İlgili veriyi repository katmanında okur veya yazar."""
        result = await self.db.execute(
            update(NotificationItem)
            .where(
                NotificationItem.recipient_id == recipient_id,
                NotificationItem.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        await self.db.flush()
        return result.rowcount


# ===================================================================
# Clinical notes
# ===================================================================

class SqliteClinicalNoteRepo(AbstractClinicalNoteRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        n = ClinicalNote(**data)
        self.db.add(n)
        await self.db.flush()
        await self.db.refresh(n)
        return _note_to_dict(n)

    async def get_by_id(self, note_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(ClinicalNote).where(ClinicalNote.id == note_id))
        n = r.scalar_one_or_none()
        return _note_to_dict(n) if n else None

    async def update(self, note_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(ClinicalNote).where(ClinicalNote.id == note_id))
        n = r.scalar_one_or_none()
        if n is None:
            return None
        for k, v in data.items():
            setattr(n, k, v)
        self.db.add(n)
        await self.db.flush()
        await self.db.refresh(n)
        return _note_to_dict(n)

    async def delete(self, note_id: str) -> bool:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(ClinicalNote).where(ClinicalNote.id == note_id))
        n = r.scalar_one_or_none()
        if n is None:
            return False
        await self.db.delete(n)
        await self.db.flush()
        return True

    async def list_by_patient(self, patient_id: str, doctor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        q = select(ClinicalNote).where(ClinicalNote.patient_id == patient_id)
        if doctor_id:
            q = q.where(ClinicalNote.doctor_id == doctor_id)
        q = q.order_by(ClinicalNote.created_at.desc())
        r = await self.db.execute(q)
        return [_note_to_dict(n) for n in r.scalars().all()]


# ===================================================================
# App settings
# ===================================================================

class SqliteSettingsRepo(AbstractSettingsRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = AppSettings(user_id=user_id)
            self.db.add(s)
            await self.db.flush()
            await self.db.refresh(s)
        return _settings_to_dict(s)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = AppSettings(user_id=user_id)
            self.db.add(s)
        for k, v in data.items():
            if v is not None:
                setattr(s, k, v)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _settings_to_dict(s)


# ===================================================================
# Simulation state
# ===================================================================

class SqliteSimulationStateRepo(AbstractSimulationStateRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(SimulationState).where(SimulationState.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = SimulationState(user_id=user_id, scenario_index=0, tick_count=0)
            self.db.add(s)
            await self.db.flush()
            await self.db.refresh(s)
        return _sim_to_dict(s)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(select(SimulationState).where(SimulationState.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = SimulationState(user_id=user_id, scenario_index=0, tick_count=0)
            self.db.add(s)
        for k, v in data.items():
            setattr(s, k, v)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _sim_to_dict(s)


# ===================================================================
# Device registration & packet logs
# ===================================================================

class SqliteDeviceRepo(AbstractDeviceRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def register_device(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        reg = DeviceRegistration(**data)
        self.db.add(reg)
        await self.db.flush()
        await self.db.refresh(reg)
        return {
            "id": reg.id, "device_id": reg.device_id,
            "user_id": reg.user_id, "registered_at": reg.registered_at,
            "is_active": reg.is_active,
        }

    async def get_registration(self, device_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(DeviceRegistration).where(
                DeviceRegistration.device_id == device_id,
                DeviceRegistration.is_active == True,  # noqa: E712
            )
        )
        reg = r.scalar_one_or_none()
        if reg is None:
            return None
        return {
            "id": reg.id, "device_id": reg.device_id,
            "user_id": reg.user_id, "registered_at": reg.registered_at,
            "is_active": reg.is_active,
        }

    async def update_registration(self, device_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(DeviceRegistration).where(DeviceRegistration.device_id == device_id)
        )
        reg = r.scalar_one_or_none()
        if reg is None:
            return None
        for k, v in data.items():
            setattr(reg, k, v)
        self.db.add(reg)
        await self.db.flush()
        await self.db.refresh(reg)
        return {
            "id": reg.id, "device_id": reg.device_id,
            "user_id": reg.user_id, "registered_at": reg.registered_at,
            "is_active": reg.is_active,
        }

    async def log_packet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        log = DevicePacketLog(**data)
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return {"id": log.id, "device_id": log.device_id, "packet_seq": log.packet_seq}


# ===================================================================
# User baseline
# ===================================================================

def _baseline_to_dict(b: UserBaseline) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": b.id,
        "user_id": b.user_id,
        "hr_mean": b.hr_mean,
        "hr_std": b.hr_std,
        "spo2_mean": b.spo2_mean,
        "spo2_std": b.spo2_std,
        "motion_mean": b.motion_mean,
        "motion_std": b.motion_std,
        "ppg_quality_mean": b.ppg_quality_mean,
        "sample_count": b.sample_count,
        "is_ready": b.is_ready,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
        "last_updated": b.last_updated,
    }


class SqliteBaselineRepo(AbstractBaselineRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserBaseline).where(UserBaseline.user_id == user_id)
        )
        b = r.scalar_one_or_none()
        return _baseline_to_dict(b) if b else None

    async def create_for_user(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        b = UserBaseline(id=str(uuid4()), user_id=user_id)
        self.db.add(b)
        await self.db.flush()
        await self.db.refresh(b)
        return _baseline_to_dict(b)

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        existing = await self.get_by_user_id(user_id)
        if existing is not None:
            return existing
        return await self.create_for_user(user_id)

    async def update_values(self, user_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserBaseline).where(UserBaseline.user_id == user_id)
        )
        b = r.scalar_one_or_none()
        if b is None:
            b = UserBaseline(id=str(uuid4()), user_id=user_id)
            self.db.add(b)
        for k, v in values.items():
            setattr(b, k, v)
        self.db.add(b)
        await self.db.flush()
        await self.db.refresh(b)
        return _baseline_to_dict(b)


# ===================================================================
# Part 5A — Learning Loop
# ===================================================================

def _capture_session_to_dict(s: LearningCaptureSession) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": s.id, "user_id": s.user_id, "device_id": s.device_id,
        "started_at": s.started_at, "ended_at": s.ended_at,
        "source": s.source, "mode": s.mode,
        "sample_count": s.sample_count,
        "quality_sample_count": s.quality_sample_count,
        "low_quality_sample_count": s.low_quality_sample_count,
        "event_count": s.event_count,
        "has_user_feedback": s.has_user_feedback,
        "training_candidate": s.training_candidate,
        "training_status": s.training_status,
        "created_at": s.created_at, "updated_at": s.updated_at,
    }


def _learning_window_to_dict(w: LearningWindow) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    def _parse_json(val):
        """İlgili veriyi repository katmanında okur veya yazar."""
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except Exception:
            return None

    return {
        "id": w.id, "user_id": w.user_id, "device_id": w.device_id,
        "session_id": w.session_id,
        "window_start_at": w.window_start_at, "window_end_at": w.window_end_at,
        "duration_sec": w.duration_sec, "sample_count": w.sample_count,
        "source": w.source, "risk_level_at_capture": w.risk_level_at_capture,
        "final_risk_score": w.final_risk_score,
        "quality_confidence": w.quality_confidence,
        "baseline_ready": w.baseline_ready,
        "ml_shadow_summary": _parse_json(w.ml_shadow_summary),
        "retrieval_shadow_summary": _parse_json(w.retrieval_shadow_summary),
        "assistant_mode": w.assistant_mode,
        "user_feedback_label": w.user_feedback_label,
        "suggested_label": w.suggested_label,
        "label_confidence": w.label_confidence,
        "training_candidate": w.training_candidate,
        "exported_at": w.exported_at,
        "created_at": w.created_at,
    }


def _feedback_to_dict(f: UserFeedbackEvent) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": f.id, "user_id": f.user_id,
        "related_window_id": f.related_window_id,
        "related_alert_id": f.related_alert_id,
        "feedback_type": f.feedback_type,
        "feedback_source": f.feedback_source,
        "note": f.note, "created_at": f.created_at,
    }


def _model_version_to_dict(m: ModelVersionRegistry) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    def _parse_json(val):
        """İlgili veriyi repository katmanında okur veya yazar."""
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except Exception:
            return None

    return {
        "id": m.id, "model_name": m.model_name, "version": m.version,
        "model_path": m.model_path,
        "training_data_snapshot": m.training_data_snapshot,
        "metrics_json": _parse_json(m.metrics_json),
        "status": m.status,
        "created_at": m.created_at, "activated_at": m.activated_at,
    }


class SqliteLearningRepo(AbstractLearningRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def create_session(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        s = LearningCaptureSession(**data)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _capture_session_to_dict(s)

    async def close_session(self, session_id: str, ended_at) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(LearningCaptureSession).where(LearningCaptureSession.id == session_id)
        )
        s = r.scalar_one_or_none()
        if s is None:
            return None
        s.ended_at = ended_at
        s.updated_at = datetime.utcnow()
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _capture_session_to_dict(s)

    async def create_window(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Serialize JSON fields
        """İlgili veriyi repository katmanında okur veya yazar."""
        for field in ("ml_shadow_summary", "retrieval_shadow_summary"):
            if isinstance(data.get(field), dict):
                data[field] = json.dumps(data[field])
        w = LearningWindow(**data)
        self.db.add(w)
        await self.db.flush()
        await self.db.refresh(w)
        return _learning_window_to_dict(w)

    async def list_windows(
        self,
        user_id: Optional[str] = None,
        training_candidate: Optional[bool] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        q = select(LearningWindow).order_by(LearningWindow.created_at.desc())
        if user_id:
            q = q.where(LearningWindow.user_id == user_id)
        if training_candidate is not None:
            q = q.where(LearningWindow.training_candidate == training_candidate)
        if source:
            q = q.where(LearningWindow.source == source)
        q = q.limit(limit)
        r = await self.db.execute(q)
        return [_learning_window_to_dict(w) for w in r.scalars().all()]

    async def get_window(self, window_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(LearningWindow).where(LearningWindow.id == window_id)
        )
        w = r.scalar_one_or_none()
        return _learning_window_to_dict(w) if w else None

    async def mark_window_candidate(
        self, window_id: str, status: str
    ) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(LearningWindow).where(LearningWindow.id == window_id)
        )
        w = r.scalar_one_or_none()
        if w is None:
            return None
        is_candidate = status in ("candidate", "approved")
        w.training_candidate = is_candidate
        w.suggested_label = w.suggested_label  # unchanged
        self.db.add(w)
        await self.db.flush()
        await self.db.refresh(w)
        return _learning_window_to_dict(w)

    async def update_window_feedback(
        self, window_id: str, feedback_label: str
    ) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(LearningWindow).where(LearningWindow.id == window_id)
        )
        w = r.scalar_one_or_none()
        if w is None:
            return None
        w.user_feedback_label = feedback_label
        # sensor_error feedback → exclude from training
        if feedback_label == "sensor_error":
            w.training_candidate = False
        self.db.add(w)
        await self.db.flush()
        await self.db.refresh(w)
        return _learning_window_to_dict(w)

    async def create_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        f = UserFeedbackEvent(**data)
        self.db.add(f)
        await self.db.flush()
        await self.db.refresh(f)
        return _feedback_to_dict(f)

    async def get_feedback_for_window(self, window_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(UserFeedbackEvent)
            .where(UserFeedbackEvent.related_window_id == window_id)
            .order_by(UserFeedbackEvent.created_at.desc())
        )
        return [_feedback_to_dict(f) for f in r.scalars().all()]

    async def create_model_version(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        if isinstance(data.get("metrics_json"), dict):
            data["metrics_json"] = json.dumps(data["metrics_json"])
        m = ModelVersionRegistry(**data)
        self.db.add(m)
        await self.db.flush()
        await self.db.refresh(m)
        return _model_version_to_dict(m)

    async def list_model_versions(self) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(ModelVersionRegistry).order_by(ModelVersionRegistry.created_at.desc())
        )
        return [_model_version_to_dict(m) for m in r.scalars().all()]

    async def get_active_model_version(self) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(ModelVersionRegistry)
            .where(ModelVersionRegistry.status == "active")
            .order_by(ModelVersionRegistry.activated_at.desc())
        )
        m = r.scalars().first()
        return _model_version_to_dict(m) if m else None

    async def list_windows_for_export(
        self,
        user_id: Optional[str] = None,
        include_demo: bool = False,
        min_quality_confidence: float = 0.0,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        q = (
            select(LearningWindow)
            .where(
                LearningWindow.training_candidate == True,  # noqa: E712
                LearningWindow.exported_at == None,         # noqa: E711
                LearningWindow.quality_confidence >= min_quality_confidence,
            )
            .order_by(LearningWindow.created_at.asc())
        )
        if user_id:
            q = q.where(LearningWindow.user_id == user_id)
        if not include_demo:
            q = q.where(LearningWindow.source != "demo")
        q = q.limit(limit)
        r = await self.db.execute(q)
        return [_learning_window_to_dict(w) for w in r.scalars().all()]

    async def mark_windows_exported(self, window_ids: List[str]) -> int:
        """İlgili veriyi repository katmanında okur veya yazar."""
        if not window_ids:
            return 0
        now = datetime.utcnow()
        result = await self.db.execute(
            update(LearningWindow)
            .where(LearningWindow.id.in_(window_ids))
            .values(exported_at=now)
        )
        await self.db.flush()
        return result.rowcount


# ---------------------------------------------------------------------------
# Part 5B � Adaptive Personalization repository (SQLite)
# ---------------------------------------------------------------------------

def _profile_to_dict(p: PersonalHealthProfile) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    import json as _json
    return {
        "id": p.id,
        "user_id": p.user_id,
        "baseline_id": p.baseline_id,
        "personalization_level": p.personalization_level,
        "total_observation_minutes": p.total_observation_minutes,
        "total_valid_samples": p.total_valid_samples,
        "total_feedback_count": p.total_feedback_count,
        "false_alarm_count": p.false_alarm_count,
        "confirmed_risk_count": p.confirmed_risk_count,
        "sensor_error_count": p.sensor_error_count,
        "typical_hr_min": p.typical_hr_min,
        "typical_hr_max": p.typical_hr_max,
        "typical_spo2_min": p.typical_spo2_min,
        "typical_spo2_max": p.typical_spo2_max,
        "typical_motion_min": p.typical_motion_min,
        "typical_motion_max": p.typical_motion_max,
        "day_profile_json": _json.loads(p.day_profile_json) if p.day_profile_json else None,
        "night_profile_json": _json.loads(p.night_profile_json) if p.night_profile_json else None,
        "activity_profile_json": _json.loads(p.activity_profile_json) if p.activity_profile_json else None,
        "ml_window_count": p.ml_window_count,
        "ml_usable_window_count": p.ml_usable_window_count,
        "ml_evidence_mean": p.ml_evidence_mean,
        "ml_evidence_std": p.ml_evidence_std,
        "ml_confidence_mean": p.ml_confidence_mean,
        "ml_positive_support_count": p.ml_positive_support_count,
        "ml_personal_disagreement_count": p.ml_personal_disagreement_count,
        "last_ml_evidence_score": p.last_ml_evidence_score,
        "last_ml_adjustment": p.last_ml_adjustment,
        "last_model_window_at": p.last_model_window_at,
        "last_recalibrated_at": p.last_recalibrated_at,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _risk_memory_to_dict(m: PersonalRiskMemory) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    import json as _json
    return {
        "id": m.id,
        "user_id": m.user_id,
        "event_type": m.event_type,
        "risk_score": m.risk_score,
        "severity": m.severity,
        "context_json": _json.loads(m.context_json) if m.context_json else None,
        "created_at": m.created_at,
    }


def _trend_to_dict(t: PersonalTrendSnapshot) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": t.id,
        "user_id": t.user_id,
        "window_minutes": t.window_minutes,
        "hr_trend": t.hr_trend,
        "spo2_trend": t.spo2_trend,
        "motion_trend": t.motion_trend,
        "quality_trend": t.quality_trend,
        "risk_trend": t.risk_trend,
        "trend_confidence": t.trend_confidence,
        "created_at": t.created_at,
    }


class SqlitePersonalizationRepo(AbstractPersonalizationRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession):
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_or_create_profile(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(PersonalHealthProfile).where(PersonalHealthProfile.user_id == user_id)
        )
        p = r.scalar_one_or_none()
        if p is None:
            p = PersonalHealthProfile(id=str(uuid4()), user_id=user_id)
            self.db.add(p)
            await self.db.flush()
            await self.db.refresh(p)
        return _profile_to_dict(p)

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        import json as _json
        r = await self.db.execute(
            select(PersonalHealthProfile).where(PersonalHealthProfile.user_id == user_id)
        )
        p = r.scalar_one_or_none()
        if p is None:
            p = PersonalHealthProfile(id=str(uuid4()), user_id=user_id)
            self.db.add(p)
        for k, v in updates.items():
            if k in ("day_profile_json", "night_profile_json", "activity_profile_json"):
                setattr(p, k, _json.dumps(v) if v is not None else None)
            else:
                setattr(p, k, v)
        p.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(p)
        return _profile_to_dict(p)

    async def add_risk_memory(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        import json as _json
        raw = dict(data)
        if isinstance(raw.get("context_json"), dict):
            raw["context_json"] = _json.dumps(raw["context_json"])
        m = PersonalRiskMemory(**raw)
        self.db.add(m)
        await self.db.flush()
        await self.db.refresh(m)
        return _risk_memory_to_dict(m)

    async def list_risk_memory(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(PersonalRiskMemory)
            .where(PersonalRiskMemory.user_id == user_id)
            .order_by(PersonalRiskMemory.created_at.desc())
            .limit(limit)
        )
        return [_risk_memory_to_dict(m) for m in r.scalars().all()]

    async def create_trend_snapshot(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        t = PersonalTrendSnapshot(**data)
        self.db.add(t)
        await self.db.flush()
        await self.db.refresh(t)
        return _trend_to_dict(t)

    async def get_latest_trend_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(PersonalTrendSnapshot)
            .where(PersonalTrendSnapshot.user_id == user_id)
            .order_by(PersonalTrendSnapshot.created_at.desc())
            .limit(1)
        )
        t = r.scalar_one_or_none()
        return _trend_to_dict(t) if t else None

    async def summarize_personalization(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        profile = await self.get_or_create_profile(user_id)
        latest_trend = await self.get_latest_trend_snapshot(user_id)
        total_fb = profile["total_feedback_count"]
        false_alarm_rate = (
            round(profile["false_alarm_count"] / total_fb, 3) if total_fb > 0 else 0.0
        )
        return {
            "user_id": user_id,
            "personalization_level": profile["personalization_level"],
            "total_valid_samples": profile["total_valid_samples"],
            "total_observation_minutes": profile["total_observation_minutes"],
            "false_alarm_rate": false_alarm_rate,
            "confirmed_risk_count": profile["confirmed_risk_count"],
            "feedback_count": total_fb,
            "latest_trend": latest_trend,
            "typical_ranges": {
                "hr": [profile["typical_hr_min"], profile["typical_hr_max"]],
                "spo2": [profile["typical_spo2_min"], profile["typical_spo2_max"]],
                "motion": [profile["typical_motion_min"], profile["typical_motion_max"]],
            },
        }


# ---------------------------------------------------------------------------
# Part 5C — Care Assistant Orchestrator SQLite repo
# ---------------------------------------------------------------------------

def _state_to_dict(s: AssistantState) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    import json as _json
    d = {
        "id": s.id, "user_id": s.user_id,
        "current_mode": s.current_mode, "previous_mode": s.previous_mode,
        "last_risk_score": s.last_risk_score, "last_severity": s.last_severity,
        "personalization_level": s.personalization_level,
        "watch_started_at": s.watch_started_at,
        "warning_started_at": s.warning_started_at,
        "critical_started_at": s.critical_started_at,
        "awaiting_user_ack": s.awaiting_user_ack,
        "ack_deadline_at": s.ack_deadline_at,
        "last_user_response": s.last_user_response,
        "last_action_summary": None,
        "monitoring_intensity": s.monitoring_intensity,
        "recommended_poll_interval_sec": s.recommended_poll_interval_sec,
        "created_at": s.created_at, "updated_at": s.updated_at,
    }
    if s.last_action_summary:
        try:
            d["last_action_summary"] = _json.loads(s.last_action_summary)
        except Exception:
            d["last_action_summary"] = s.last_action_summary
    return d


def _action_to_dict(a: AssistantAction) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    import json as _json
    d = {
        "id": a.id, "user_id": a.user_id, "state_id": a.state_id,
        "mode": a.mode, "action_type": a.action_type, "message": a.message,
        "priority": a.priority, "requires_ack": a.requires_ack,
        "ack_options": None, "created_at": a.created_at,
        "expires_at": a.expires_at, "completed_at": a.completed_at,
        "metadata_json": None,
    }
    if a.ack_options:
        try:
            d["ack_options"] = _json.loads(a.ack_options)
        except Exception:
            d["ack_options"] = a.ack_options
    if a.metadata_json:
        try:
            d["metadata_json"] = _json.loads(a.metadata_json)
        except Exception:
            d["metadata_json"] = a.metadata_json
    return d


def _ack_to_dict(a: AssistantAcknowledgement) -> Dict[str, Any]:
    """İlgili veriyi repository katmanında okur veya yazar."""
    return {
        "id": a.id, "user_id": a.user_id, "state_id": a.state_id,
        "action_id": a.action_id, "response": a.response,
        "response_source": a.response_source, "note": a.note,
        "created_at": a.created_at,
    }


class SqliteAssistantRepo(AbstractAssistantRepo):
    """İlgili veri kaynağı için repository davranışını tanımlar."""
    def __init__(self, db: AsyncSession) -> None:
        """İlgili veriyi repository katmanında okur veya yazar."""
        self.db = db

    async def get_or_create_state(self, user_id: str) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AssistantState).where(AssistantState.user_id == user_id)
        )
        s = r.scalar_one_or_none()
        if s is None:
            s = AssistantState(
                id=str(uuid4()), user_id=user_id,
                current_mode="normal", monitoring_intensity="normal",
                recommended_poll_interval_sec=60,
            )
            self.db.add(s)
            await self.db.flush()
            await self.db.refresh(s)
        return _state_to_dict(s)

    async def update_state(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        import json as _json
        r = await self.db.execute(
            select(AssistantState).where(AssistantState.user_id == user_id)
        )
        s = r.scalar_one_or_none()
        if s is None:
            s = AssistantState(id=str(uuid4()), user_id=user_id)
            self.db.add(s)
        for k, v in updates.items():
            if k == "last_action_summary" and isinstance(v, dict):
                v = _json.dumps(v)
            setattr(s, k, v)
        s.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(s)
        return _state_to_dict(s)

    async def create_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        import json as _json
        raw = dict(data)
        if isinstance(raw.get("ack_options"), dict):
            raw["ack_options"] = _json.dumps(raw["ack_options"])
        if isinstance(raw.get("metadata_json"), dict):
            raw["metadata_json"] = _json.dumps(raw["metadata_json"])
        a = AssistantAction(**raw)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _action_to_dict(a)

    async def list_active_actions(self, user_id: str) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AssistantAction)
            .where(
                AssistantAction.user_id == user_id,
                AssistantAction.completed_at.is_(None),
            )
            .order_by(AssistantAction.created_at.desc())
        )
        return [_action_to_dict(a) for a in r.scalars().all()]

    async def complete_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AssistantAction).where(AssistantAction.id == action_id)
        )
        a = r.scalar_one_or_none()
        if a:
            a.completed_at = datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(a)
            return _action_to_dict(a)
        return None

    async def create_ack(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        raw = dict(data)
        a = AssistantAcknowledgement(**raw)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _ack_to_dict(a)

    async def get_due_ack_timeouts(self, now: datetime) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AssistantState)
            .where(
                AssistantState.awaiting_user_ack == True,
                AssistantState.ack_deadline_at <= now,
            )
        )
        return [_state_to_dict(s) for s in r.scalars().all()]

    async def list_assistant_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """İlgili veriyi repository katmanında okur veya yazar."""
        r = await self.db.execute(
            select(AssistantAction)
            .where(AssistantAction.user_id == user_id)
            .order_by(AssistantAction.created_at.desc())
            .limit(limit)
        )
        return [_action_to_dict(a) for a in r.scalars().all()]
