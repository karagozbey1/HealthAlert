# Firestore repository methods use the sync client via executors so they
# don't block the async event loop.
# Firestore repository siniflari senkron istemciyi async akisa uyarlayarak kullanir.
# Koleksiyon adlari SQLAlchemy tarafindaki tablo yapisiyla esitlenmistir.
from __future__ import annotations

import asyncio
from datetime import datetime
from functools import partial
from typing import Any, Dict, List, Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from repositories.base import (
    AbstractAlertRepo,
    AbstractAnomalyRepo,
    AbstractBaselineRepo,
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


# Bloklayici Firestore cagrilarini varsayilan executor uzerinden calistirir.
def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


# Firestore dokumanini id alani eklenmis duz dict yapisina cevirir.
def _doc_to_dict(doc) -> Dict[str, Any]:
    d = doc.to_dict()
    d["id"] = doc.id
    return d


# Python datetime nesnesini Firestore istemcisine dogrudan iletir.
def _ts(dt: datetime | None) -> Any:
    return dt


# ===================================================================
# User
# ===================================================================

class FirebaseUserRepo(AbstractUserRepo):
    COLLECTION = "users"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(user_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("email", "==", email))
            .limit(1)
            .get
        )
        return _doc_to_dict(docs[0]) if docs else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id") or data.get("user_id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def list_by_role(self, role: str) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("role", "==", role))
            .get
        )
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# Link codes
# ===================================================================

class FirebaseLinkCodeRepo(AbstractLinkCodeRepo):
    COLLECTION = "link_codes"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_id(self, code_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(code_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("code", "==", code))
            .limit(1)
            .get
        )
        return _doc_to_dict(docs[0]) if docs else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def update(self, code_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(code_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def list_by_owner(self, owner_id: str) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("owner_id", "==", owner_id))
            .order_by("created_at", direction="DESCENDING")
            .get
        )
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# Relations
# ===================================================================

class FirebaseRelationRepo(AbstractRelationRepo):
    COLLECTION = "user_relations"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_id(self, relation_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(relation_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def update(self, relation_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(relation_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def find_active_by_self_user(self, self_user_id: str) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("self_user_id", "==", self_user_id))
            .where(filter=FieldFilter("is_active", "==", True))
            .get
        )
        return [_doc_to_dict(d) for d in docs]

    async def find_active_by_linked_user(self, linked_user_id: str) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("linked_user_id", "==", linked_user_id))
            .where(filter=FieldFilter("is_active", "==", True))
            .get
        )
        return [_doc_to_dict(d) for d in docs]

    async def find_active_link(self, self_user_id: str, linked_user_id: str) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("self_user_id", "==", self_user_id))
            .where(filter=FieldFilter("linked_user_id", "==", linked_user_id))
            .where(filter=FieldFilter("is_active", "==", True))
            .limit(1)
            .get
        )
        return _doc_to_dict(docs[0]) if docs else None


# ===================================================================
# Live status
# ===================================================================

class FirebaseLiveStatusRepo(AbstractLiveStatusRepo):
    COLLECTION = "live_statuses"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(user_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def upsert(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        merged = {"user_id": user_id, **data}
        await _run_sync(ref.set, merged, merge=True)
        doc = await _run_sync(ref.get)
        return _doc_to_dict(doc)


# ===================================================================
# Anomaly events
# ===================================================================

class FirebaseAnomalyRepo(AbstractAnomalyRepo):
    COLLECTION = "anomaly_events"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .order_by("detected_at", direction="DESCENDING")
            .limit(limit)
            .get
        )
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# Alert events
# ===================================================================

class FirebaseAlertRepo(AbstractAlertRepo):
    COLLECTION = "alert_events"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(alert_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def update(self, alert_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(alert_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
            .get
        )
        return [_doc_to_dict(d) for d in docs]

    async def get_active_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        # Firestore doesn't support "not in", so query non-terminal statuses
        for status in ("countdown", "raised", "escalated", "post_event_monitoring"):
            docs = await _run_sync(
                self.fs.collection(self.COLLECTION)
                .where(filter=FieldFilter("user_id", "==", user_id))
                .where(filter=FieldFilter("status", "==", status))
                .limit(1)
                .get
            )
            if docs:
                return _doc_to_dict(docs[0])
        return None

    async def get_countdown_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("status", "==", "countdown"))
            .get
        )
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# Post-event sessions
# ===================================================================

class FirebasePostEventRepo(AbstractPostEventRepo):
    COLLECTION = "post_event_sessions"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(session_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def update(self, session_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(session_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)


# ===================================================================
# History items
# ===================================================================

class FirebaseHistoryRepo(AbstractHistoryRepo):
    COLLECTION = "history_items"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def list_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .get
        )
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# Notifications
# ===================================================================

class FirebaseNotificationRepo(AbstractNotificationRepo):
    COLLECTION = "notification_items"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def list_by_recipient(self, recipient_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("recipient_id", "==", recipient_id))
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
            .get
        )
        return [_doc_to_dict(d) for d in docs]

    async def mark_read(self, notif_id: str, recipient_id: str) -> bool:
        ref = self.fs.collection(self.COLLECTION).document(notif_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return False
        d = doc.to_dict()
        if d.get("recipient_id") != recipient_id:
            return False
        await _run_sync(ref.update, {"is_read": True})
        return True

    async def mark_all_read(self, recipient_id: str) -> int:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("recipient_id", "==", recipient_id))
            .where(filter=FieldFilter("is_read", "==", False))
            .get
        )
        batch = self.fs.batch()
        for doc in docs:
            batch.update(doc.reference, {"is_read": True})
        await _run_sync(batch.commit)
        return len(docs)


# ===================================================================
# Clinical notes
# ===================================================================

class FirebaseClinicalNoteRepo(AbstractClinicalNoteRepo):
    COLLECTION = "clinical_notes"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def get_by_id(self, note_id: str) -> Optional[Dict[str, Any]]:
        doc = await _run_sync(self.fs.collection(self.COLLECTION).document(note_id).get)
        return _doc_to_dict(doc) if doc.exists else None

    async def update(self, note_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = self.fs.collection(self.COLLECTION).document(note_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return None
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def delete(self, note_id: str) -> bool:
        ref = self.fs.collection(self.COLLECTION).document(note_id)
        doc = await _run_sync(ref.get)
        if not doc.exists:
            return False
        await _run_sync(ref.delete)
        return True

    async def list_by_patient(self, patient_id: str, doctor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self.fs.collection(self.COLLECTION).where(filter=FieldFilter("patient_id", "==", patient_id))
        if doctor_id:
            q = q.where(filter=FieldFilter("doctor_id", "==", doctor_id))
        q = q.order_by("created_at", direction="DESCENDING")
        docs = await _run_sync(q.get)
        return [_doc_to_dict(d) for d in docs]


# ===================================================================
# App settings
# ===================================================================

class FirebaseSettingsRepo(AbstractSettingsRepo):
    COLLECTION = "app_settings"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        doc = await _run_sync(ref.get)
        if doc.exists:
            d = doc.to_dict()
            d["user_id"] = user_id
            return d
        defaults = {
            "user_id": user_id,
            "notifications_enabled": True,
            "battery_mode": "balanced",
            "background_monitoring": True,
            "update_interval_seconds": 4,
        }
        await _run_sync(ref.set, defaults)
        return defaults

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        clean = {k: v for k, v in data.items() if v is not None}
        await _run_sync(ref.set, clean, merge=True)
        doc = await _run_sync(ref.get)
        d = doc.to_dict()
        d["user_id"] = user_id
        return d


# ===================================================================
# Simulation state
# ===================================================================

class FirebaseSimulationStateRepo(AbstractSimulationStateRepo):
    COLLECTION = "simulation_states"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        doc = await _run_sync(ref.get)
        if doc.exists:
            d = doc.to_dict()
            d["user_id"] = user_id
            return d
        defaults = {
            "user_id": user_id,
            "scenario_index": 0,
            "tick_count": 0,
            "last_updated": datetime.utcnow(),
        }
        await _run_sync(ref.set, defaults)
        return defaults

    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ref = self.fs.collection(self.COLLECTION).document(user_id)
        await _run_sync(ref.set, data, merge=True)
        doc = await _run_sync(ref.get)
        d = doc.to_dict()
        d["user_id"] = user_id
        return d


# ===================================================================
# Device registration & packet logs
# ===================================================================

class FirebaseDeviceRepo(AbstractDeviceRepo):
    REG_COLLECTION = "device_registrations"
    LOG_COLLECTION = "device_packet_logs"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def register_device(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id") or data.get("device_id")
        ref = self.fs.collection(self.REG_COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {**data, "id": doc_id}

    async def get_registration(self, device_id: str) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.REG_COLLECTION)
            .where(filter=FieldFilter("device_id", "==", device_id))
            .where(filter=FieldFilter("is_active", "==", True))
            .limit(1)
            .get
        )
        return _doc_to_dict(docs[0]) if docs else None

    async def update_registration(self, device_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.REG_COLLECTION)
            .where(filter=FieldFilter("device_id", "==", device_id))
            .limit(1)
            .get
        )
        if not docs:
            return None
        ref = docs[0].reference
        await _run_sync(ref.update, data)
        updated = await _run_sync(ref.get)
        return _doc_to_dict(updated)

    async def log_packet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id")
        ref = self.fs.collection(self.LOG_COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return {"id": doc_id, "device_id": data.get("device_id"), "packet_seq": data.get("packet_seq")}


# ===================================================================
# User Baseline
# ===================================================================

class FirebaseBaselineRepo(AbstractBaselineRepo):
    COLLECTION = "user_baselines"

    def __init__(self, fs_client):
        self.fs = fs_client

    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .limit(1)
            .get
        )
        return _doc_to_dict(docs[0]) if docs else None

    async def create_for_user(self, user_id: str) -> Dict[str, Any]:
        from uuid import uuid4
        from datetime import datetime
        doc_id = str(uuid4())
        now = datetime.utcnow()
        data = {
            "id": doc_id,
            "user_id": user_id,
            "hr_mean": 72.0,
            "hr_std": 10.0,
            "spo2_mean": 98.0,
            "spo2_std": 1.5,
            "motion_mean": 0.10,
            "motion_std": 0.08,
            "ppg_quality_mean": 0.85,
            "sample_count": 0,
            "is_ready": False,
            "created_at": now,
            "updated_at": now,
            "last_updated": None,
        }
        ref = self.fs.collection(self.COLLECTION).document(doc_id)
        await _run_sync(ref.set, data)
        return data

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        existing = await self.get_by_user_id(user_id)
        if existing is not None:
            return existing
        return await self.create_for_user(user_id)

    async def update_values(self, user_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
        docs = await _run_sync(
            self.fs.collection(self.COLLECTION)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .limit(1)
            .get
        )
        if docs:
            ref = docs[0].reference
            await _run_sync(ref.update, values)
            updated = await _run_sync(ref.get)
            return _doc_to_dict(updated)
        data = await self.create_for_user(user_id)
        if values:
            ref = self.fs.collection(self.COLLECTION).document(data["id"])
            await _run_sync(ref.update, values)
            updated = await _run_sync(ref.get)
            return _doc_to_dict(updated)
        return data
