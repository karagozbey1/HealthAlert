"""
SQLite concrete repository implementations.

Each class accepts an ``AsyncSession`` and wraps the existing SQLAlchemy
ORM patterns that were previously inline in routers.
"""
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
    ClinicalNote,
    DevicePacketLog,
    DeviceRegistration,
    HistoryItem,
    LinkCode,
    LiveStatus,
    NotificationItem,
    PostEventSession,
    SimulationState,
    User,
    UserRelation,
)
from repositories.base import (
    AbstractAlertRepo,
    AbstractAnomalyRepo,
    AbstractClinicalNoteRepo,
    AbstractDeviceRepo,
    AbstractHistoryRepo,
    AbstractLinkCodeRepo,
    AbstractLiveStatusRepo,
    AbstractNotificationRepo,
    AbstractPostEventRepo,
    AbstractRelationRepo,
    AbstractSettingsRepo,
    AbstractSimulationStateRepo,
    AbstractUserRepo,
)


def _user_to_dict(u: User) -> Dict[str, Any]:
    return {
        "id": u.id, "email": u.email, "password_hash": u.password_hash,
        "role": u.role, "full_name": u.full_name, "phone": u.phone,
        "birth_date": u.birth_date, "created_at": u.created_at,
    }


def _code_to_dict(c: LinkCode) -> Dict[str, Any]:
    return {
        "id": c.id, "code": c.code, "owner_id": c.owner_id,
        "code_type": c.code_type, "is_active": c.is_active,
        "uses_remaining": c.uses_remaining, "expires_at": c.expires_at,
        "created_at": c.created_at,
    }


def _rel_to_dict(r: UserRelation) -> Dict[str, Any]:
    return {
        "id": r.id, "self_user_id": r.self_user_id,
        "linked_user_id": r.linked_user_id, "relation_type": r.relation_type,
        "is_active": r.is_active, "created_at": r.created_at,
        "revoked_at": r.revoked_at,
    }


def _live_to_dict(ls: LiveStatus) -> Dict[str, Any]:
    return {
        "id": ls.id, "user_id": ls.user_id, "heart_rate": ls.heart_rate,
        "spo2": ls.spo2, "motion_score": ls.motion_score,
        "risk_score": ls.risk_score, "scenario": ls.scenario,
        "timestamp": ls.timestamp,
    }


def _anomaly_to_dict(a: AnomalyEvent) -> Dict[str, Any]:
    return {
        "id": a.id, "user_id": a.user_id, "metric": a.metric,
        "value": a.value, "unit": a.unit, "severity": a.severity,
        "detected_at": a.detected_at, "summary": a.summary,
    }


def _alert_to_dict(a: AlertEvent) -> Dict[str, Any]:
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
    return {
        "id": s.id, "user_id": s.user_id, "alert_id": s.alert_id,
        "started_at": s.started_at, "ended_at": s.ended_at,
        "outcome": s.outcome,
    }


def _history_to_dict(h: HistoryItem) -> Dict[str, Any]:
    return {
        "id": h.id, "user_id": h.user_id, "item_type": h.item_type,
        "title": h.title, "subtitle": h.subtitle, "timestamp": h.timestamp,
        "severity": h.severity, "outcome": h.outcome,
    }


def _notif_to_dict(n: NotificationItem) -> Dict[str, Any]:
    return {
        "id": n.id, "recipient_id": n.recipient_id, "sender_id": n.sender_id,
        "title": n.title, "body": n.body, "notification_type": n.notification_type,
        "reference_id": n.reference_id, "reference_type": n.reference_type,
        "is_read": n.is_read, "created_at": n.created_at,
    }


def _note_to_dict(n: ClinicalNote) -> Dict[str, Any]:
    return {
        "id": n.id, "doctor_id": n.doctor_id, "patient_id": n.patient_id,
        "note": n.note, "recommendation": n.recommendation,
        "created_at": n.created_at, "updated_at": n.updated_at,
    }


def _settings_to_dict(s: AppSettings) -> Dict[str, Any]:
    return {
        "user_id": s.user_id,
        "notifications_enabled": s.notifications_enabled,
        "battery_mode": s.battery_mode,
        "background_monitoring": s.background_monitoring,
        "update_interval_seconds": s.update_interval_seconds,
    }


def _sim_to_dict(s: SimulationState) -> Dict[str, Any]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(User).where(User.id == user_id))
        u = r.scalar_one_or_none()
        return _user_to_dict(u) if u else None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(User).where(User.email == email))
        u = r.scalar_one_or_none()
        return _user_to_dict(u) if u else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        u = User(**data)
        self.db.add(u)
        await self.db.flush()
        await self.db.refresh(u)
        return _user_to_dict(u)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        r = await self.db.execute(select(User).where(User.role == role))
        return [_user_to_dict(u) for u in r.scalars().all()]


# ===================================================================
# Link codes
# ===================================================================

class SqliteLinkCodeRepo(AbstractLinkCodeRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, code_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(LinkCode).where(LinkCode.id == code_id))
        c = r.scalar_one_or_none()
        return _code_to_dict(c) if c else None

    async def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(LinkCode).where(LinkCode.code == code))
        c = r.scalar_one_or_none()
        return _code_to_dict(c) if c else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        c = LinkCode(**data)
        self.db.add(c)
        await self.db.flush()
        await self.db.refresh(c)
        return _code_to_dict(c)

    async def update(self, code_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        r = await self.db.execute(
            select(LinkCode).where(LinkCode.owner_id == owner_id)
            .order_by(LinkCode.created_at.desc())
        )
        return [_code_to_dict(c) for c in r.scalars().all()]


# ===================================================================
# Relations
# ===================================================================

class SqliteRelationRepo(AbstractRelationRepo):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, relation_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(UserRelation).where(UserRelation.id == relation_id))
        rel = r.scalar_one_or_none()
        return _rel_to_dict(rel) if rel else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rel = UserRelation(**data)
        self.db.add(rel)
        await self.db.flush()
        await self.db.refresh(rel)
        return _rel_to_dict(rel)

    async def update(self, relation_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        r = await self.db.execute(
            select(UserRelation).where(
                UserRelation.self_user_id == self_user_id,
                UserRelation.is_active == True,  # noqa: E712
            )
        )
        return [_rel_to_dict(rel) for rel in r.scalars().all()]

    async def find_active_by_linked_user(self, linked_user_id: str) -> List[Dict[str, Any]]:
        r = await self.db.execute(
            select(UserRelation).where(
                UserRelation.linked_user_id == linked_user_id,
                UserRelation.is_active == True,  # noqa: E712
            )
        )
        return [_rel_to_dict(rel) for rel in r.scalars().all()]

    async def find_active_link(self, self_user_id: str, linked_user_id: str) -> Optional[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(LiveStatus).where(LiveStatus.user_id == user_id))
        ls = r.scalar_one_or_none()
        return _live_to_dict(ls) if ls else None

    async def upsert(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        a = AnomalyEvent(**data)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _anomaly_to_dict(a)

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
        a = r.scalar_one_or_none()
        return _alert_to_dict(a) if a else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        recommendations = data.pop("recommendations", [])
        a = AlertEvent(**data)
        if recommendations:
            a.set_recommendations(recommendations)
        self.db.add(a)
        await self.db.flush()
        await self.db.refresh(a)
        return _alert_to_dict(a)

    async def update(self, alert_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        r = await self.db.execute(
            select(AlertEvent)
            .where(AlertEvent.user_id == user_id)
            .order_by(AlertEvent.created_at.desc())
            .limit(limit)
        )
        return [_alert_to_dict(a) for a in r.scalars().all()]

    async def get_active_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(PostEventSession).where(PostEventSession.id == session_id))
        s = r.scalar_one_or_none()
        return _post_event_to_dict(s) if s else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        s = PostEventSession(**data)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return _post_event_to_dict(s)

    async def update(self, session_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        h = HistoryItem(**data)
        self.db.add(h)
        await self.db.flush()
        await self.db.refresh(h)
        return _history_to_dict(h)

    async def list_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        n = NotificationItem(**data)
        self.db.add(n)
        await self.db.flush()
        await self.db.refresh(n)
        return _notif_to_dict(n)

    async def list_by_recipient(self, recipient_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        r = await self.db.execute(
            select(NotificationItem)
            .where(NotificationItem.recipient_id == recipient_id)
            .order_by(NotificationItem.created_at.desc())
            .limit(limit)
        )
        return [_notif_to_dict(n) for n in r.scalars().all()]

    async def mark_read(self, notif_id: str, recipient_id: str) -> bool:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        n = ClinicalNote(**data)
        self.db.add(n)
        await self.db.flush()
        await self.db.refresh(n)
        return _note_to_dict(n)

    async def get_by_id(self, note_id: str) -> Optional[Dict[str, Any]]:
        r = await self.db.execute(select(ClinicalNote).where(ClinicalNote.id == note_id))
        n = r.scalar_one_or_none()
        return _note_to_dict(n) if n else None

    async def update(self, note_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        r = await self.db.execute(select(ClinicalNote).where(ClinicalNote.id == note_id))
        n = r.scalar_one_or_none()
        if n is None:
            return False
        await self.db.delete(n)
        await self.db.flush()
        return True

    async def list_by_patient(self, patient_id: str, doctor_id: Optional[str] = None) -> List[Dict[str, Any]]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        r = await self.db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = AppSettings(user_id=user_id)
            self.db.add(s)
            await self.db.flush()
            await self.db.refresh(s)
        return _settings_to_dict(s)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        r = await self.db.execute(select(SimulationState).where(SimulationState.user_id == user_id))
        s = r.scalar_one_or_none()
        if s is None:
            s = SimulationState(user_id=user_id, scenario_index=0, tick_count=0)
            self.db.add(s)
            await self.db.flush()
            await self.db.refresh(s)
        return _sim_to_dict(s)

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_device(self, data: Dict[str, Any]) -> Dict[str, Any]:
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
        log = DevicePacketLog(**data)
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return {"id": log.id, "device_id": log.device_id, "packet_seq": log.packet_seq}
