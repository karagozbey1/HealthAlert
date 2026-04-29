"""
Module 7 – Test 06: Firebase repository unit tests (mocked Firestore)
Verifies FirebaseXxxRepo operations using a lightweight mock Firestore client.
"""
import os
import sys
import asyncio
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---- Firestore mock helpers ----

class MockDocSnapshot:
    """Simulates a Firestore DocumentSnapshot."""
    def __init__(self, doc_id, data, exists=True, reference=None):
        self.id = doc_id
        self._data = data
        self.exists = exists
        self.reference = reference

    def to_dict(self):
        return {**self._data} if self.exists else None


class MockDocRef:
    """Simulates a Firestore DocumentReference."""
    def __init__(self, doc_id, data=None, exists=False):
        self.id = doc_id
        self._data = data or {}
        self._exists = exists if data else False

    def get(self):
        return MockDocSnapshot(self.id, self._data, self._exists)

    def set(self, data, merge=False):
        if merge:
            self._data.update(data)
        else:
            self._data = {**data}
        self._exists = True

    def update(self, data):
        self._data.update(data)

    def delete(self):
        self._exists = False
        self._data = {}


class MockQuery:
    """Simulates a Firestore query result."""
    def __init__(self, docs):
        self._docs = docs

    def where(self, field=None, op_string=None, value=None, **kwargs):
        # Simple in-memory filtering
        filtered = []
        f = field
        if hasattr(field, '__str__'):
            f = str(field)
        for d in self._docs:
            data = d.to_dict()
            if data and f in data:
                if op_string == "==" and data[f] == value:
                    filtered.append(d)
                elif op_string == "!=" and data[f] != value:
                    filtered.append(d)
                elif op_string == "in" and data[f] in value:
                    filtered.append(d)
            elif data and f not in data and op_string == "!=":
                filtered.append(d)
        return MockQuery(filtered)

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        return MockQuery(self._docs[:n])

    def stream(self):
        return iter(self._docs)

    def get(self):
        return self._docs


class MockCollection:
    """Simulates a Firestore CollectionReference."""
    def __init__(self, name):
        self.name = name
        self._docs: dict = {}  # id -> MockDocRef

    def document(self, doc_id=None):
        if doc_id is None:
            import uuid
            doc_id = str(uuid.uuid4())
        if doc_id not in self._docs:
            self._docs[doc_id] = MockDocRef(doc_id)
        return self._docs[doc_id]

    def where(self, field=None, op_string=None, value=None, **kwargs):
        snapshots = [
            MockDocSnapshot(did, ref._data, ref._exists, reference=ref)
            for did, ref in self._docs.items() if ref._exists
        ]
        q = MockQuery(snapshots)
        if field is not None:
            return q.where(field, op_string, value)
        return q

    def stream(self):
        return [
            MockDocSnapshot(did, ref._data, ref._exists, reference=ref)
            for did, ref in self._docs.items() if ref._exists
        ]

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        all_docs = [
            MockDocSnapshot(did, ref._data, ref._exists, reference=ref)
            for did, ref in self._docs.items() if ref._exists
        ]
        return MockQuery(all_docs[:n])


class MockBatch:
    """Simulates a Firestore WriteBatch."""
    def __init__(self):
        self._ops = []

    def update(self, ref, data):
        self._ops.append((ref, data))

    def commit(self):
        for ref, data in self._ops:
            ref.update(data)
        count = len(self._ops)
        self._ops.clear()
        return count


class MockFirestoreClient:
    """In-memory mock of google.cloud.firestore.Client."""
    def __init__(self):
        self._collections: dict = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]

    def batch(self):
        return MockBatch()


@pytest.fixture
def fs_client():
    return MockFirestoreClient()


# ---------------------------------------------------------------
# User repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_user_create_and_get(fs_client):
    from repositories.firebase.repos import FirebaseUserRepo
    repo = FirebaseUserRepo(fs_client)
    user = await repo.create({
        "id": "fu1", "email": "fire@example.com",
        "password_hash": "h", "role": "SELF", "full_name": "Firebase User",
    })
    assert user["id"] == "fu1"
    assert user["email"] == "fire@example.com"

    fetched = await repo.get_by_id("fu1")
    assert fetched is not None
    assert fetched["full_name"] == "Firebase User"


@pytest.mark.asyncio
async def test_firebase_user_get_by_email(fs_client):
    from repositories.firebase.repos import FirebaseUserRepo
    repo = FirebaseUserRepo(fs_client)
    await repo.create({
        "id": "fu2", "email": "doctor@fire.com",
        "password_hash": "h", "role": "DOCTOR", "full_name": "Dr Firebase",
    })
    found = await repo.get_by_email("doctor@fire.com")
    assert found is not None
    assert found["role"] == "DOCTOR"


@pytest.mark.asyncio
async def test_firebase_user_update(fs_client):
    from repositories.firebase.repos import FirebaseUserRepo
    repo = FirebaseUserRepo(fs_client)
    await repo.create({
        "id": "fu3", "email": "up@fire.com",
        "password_hash": "h", "role": "SELF", "full_name": "Old",
    })
    updated = await repo.update("fu3", {"full_name": "New"})
    assert updated["full_name"] == "New"


@pytest.mark.asyncio
async def test_firebase_user_list_by_role(fs_client):
    from repositories.firebase.repos import FirebaseUserRepo
    repo = FirebaseUserRepo(fs_client)
    await repo.create({
        "id": "fu4", "email": "rel@fire.com",
        "password_hash": "h", "role": "RELATIVE", "full_name": "Relative",
    })
    result = await repo.list_by_role("RELATIVE")
    assert len(result) >= 1


# ---------------------------------------------------------------
# Notification repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_notification_cycle(fs_client):
    from repositories.firebase.repos import FirebaseNotificationRepo
    repo = FirebaseNotificationRepo(fs_client)
    n = await repo.create({
        "id": "fn1", "recipient_id": "fu1",
        "title": "Fire Notif", "body": "Hello",
        "notification_type": "alert", "is_read": False,
    })
    assert n["is_read"] is False

    marked = await repo.mark_read("fn1", "fu1")
    assert marked is True

    items = await repo.list_by_recipient("fu1")
    assert any(i["id"] == "fn1" for i in items)


@pytest.mark.asyncio
async def test_firebase_notification_mark_all_read(fs_client):
    from repositories.firebase.repos import FirebaseNotificationRepo
    repo = FirebaseNotificationRepo(fs_client)
    await repo.create({
        "id": "fn2", "recipient_id": "fu1",
        "title": "N2", "body": "B2",
        "notification_type": "info", "is_read": False,
    })
    await repo.create({
        "id": "fn3", "recipient_id": "fu1",
        "title": "N3", "body": "B3",
        "notification_type": "info", "is_read": False,
    })
    count = await repo.mark_all_read("fu1")
    assert count >= 1


# ---------------------------------------------------------------
# Alert repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_alert_create_and_active(fs_client):
    from repositories.firebase.repos import FirebaseAlertRepo
    repo = FirebaseAlertRepo(fs_client)
    alert = await repo.create({
        "id": "fa1", "user_id": "fu1",
        "title": "Fire Alert", "description": "Test",
        "severity": "warning", "status": "countdown",
        "countdown_total_sec": 30, "countdown_remaining_sec": 30,
    })
    assert alert["title"] == "Fire Alert"

    active = await repo.get_active_by_user("fu1")
    assert active is not None


@pytest.mark.asyncio
async def test_firebase_alert_update(fs_client):
    from repositories.firebase.repos import FirebaseAlertRepo
    repo = FirebaseAlertRepo(fs_client)
    await repo.create({
        "id": "fa2", "user_id": "fu1",
        "title": "A2", "description": "D2",
        "severity": "critical", "status": "countdown",
    })
    updated = await repo.update("fa2", {"status": "resolved"})
    assert updated["status"] == "resolved"


# ---------------------------------------------------------------
# History repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_history_create_and_list(fs_client):
    from repositories.firebase.repos import FirebaseHistoryRepo
    repo = FirebaseHistoryRepo(fs_client)
    h = await repo.create({
        "id": "fh1", "user_id": "fu1",
        "item_type": "alert", "title": "Resolved",
        "subtitle": "OK", "severity": "info",
    })
    assert h["item_type"] == "alert"

    items = await repo.list_by_user("fu1")
    assert len(items) >= 1


# ---------------------------------------------------------------
# Settings repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_settings_get_or_create(fs_client):
    from repositories.firebase.repos import FirebaseSettingsRepo
    repo = FirebaseSettingsRepo(fs_client)
    s = await repo.get_or_create("fu1")
    assert s["notifications_enabled"] is True

    updated = await repo.update("fu1", {"battery_mode": "power_save"})
    assert updated["battery_mode"] == "power_save"


# ---------------------------------------------------------------
# Clinical note repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_firebase_clinical_note_crud(fs_client):
    from repositories.firebase.repos import FirebaseClinicalNoteRepo
    repo = FirebaseClinicalNoteRepo(fs_client)
    note = await repo.create({
        "id": "fcn1", "doctor_id": "fu2", "patient_id": "fu1",
        "note": "OK", "recommendation": "Rest",
    })
    assert note["note"] == "OK"

    updated = await repo.update("fcn1", {"note": "Updated"})
    assert updated["note"] == "Updated"

    by_patient = await repo.list_by_patient("fu1")
    assert len(by_patient) >= 1

    deleted = await repo.delete("fcn1")
    assert deleted is True
