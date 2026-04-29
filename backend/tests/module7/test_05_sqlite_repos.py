"""
Module 7 – Test 05: SQLite repository unit tests
Uses a real async SQLite database to verify SqliteXxxRepo operations.
"""
import os
import sys
import asyncio
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Override DATABASE_URL before importing anything
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_module7.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401 – registers all models on Base.metadata

# Create test engine
_engine = create_async_engine("sqlite+aiosqlite:///./test_module7.db", echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module")
async def setup_database():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()
    # Clean up test db file
    try:
        os.remove("test_module7.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db_session(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------
# User repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_create_and_get(db_session):
    from repositories.sqlite.repos import SqliteUserRepo
    repo = SqliteUserRepo(db_session)
    user = await repo.create({
        "id": "u1", "email": "test@example.com",
        "password_hash": "hash123", "role": "SELF",
        "full_name": "Test User",
    })
    assert user["id"] == "u1"
    assert user["email"] == "test@example.com"

    fetched = await repo.get_by_id("u1")
    assert fetched is not None
    assert fetched["full_name"] == "Test User"


@pytest.mark.asyncio
async def test_user_get_by_email(db_session):
    from repositories.sqlite.repos import SqliteUserRepo
    repo = SqliteUserRepo(db_session)
    await repo.create({
        "id": "u2", "email": "email@test.com",
        "password_hash": "hash", "role": "DOCTOR",
        "full_name": "Doctor User",
    })
    found = await repo.get_by_email("email@test.com")
    assert found is not None
    assert found["role"] == "DOCTOR"


@pytest.mark.asyncio
async def test_user_update(db_session):
    from repositories.sqlite.repos import SqliteUserRepo
    repo = SqliteUserRepo(db_session)
    await repo.create({
        "id": "u3", "email": "update@test.com",
        "password_hash": "hash", "role": "SELF",
        "full_name": "Old Name",
    })
    updated = await repo.update("u3", {"full_name": "New Name"})
    assert updated["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_user_list_by_role(db_session):
    from repositories.sqlite.repos import SqliteUserRepo
    repo = SqliteUserRepo(db_session)
    await repo.create({
        "id": "u4", "email": "r1@test.com",
        "password_hash": "h", "role": "RELATIVE",
        "full_name": "Relative One",
    })
    relatives = await repo.list_by_role("RELATIVE")
    assert len(relatives) >= 1


# ---------------------------------------------------------------
# Link code repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_code_create_and_get(db_session):
    from repositories.sqlite.repos import SqliteLinkCodeRepo
    from datetime import datetime, timedelta
    repo = SqliteLinkCodeRepo(db_session)
    code = await repo.create({
        "id": "lc1", "code": "123456",
        "owner_id": "u1", "code_type": "RELATIVE",
        "is_active": True, "uses_remaining": 1,
        "expires_at": datetime.utcnow() + timedelta(hours=48),
    })
    assert code["code"] == "123456"

    by_code = await repo.get_by_code("123456")
    assert by_code is not None
    assert by_code["owner_id"] == "u1"


# ---------------------------------------------------------------
# Relation repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_relation_create_and_find(db_session):
    from repositories.sqlite.repos import SqliteRelationRepo
    repo = SqliteRelationRepo(db_session)
    rel = await repo.create({
        "id": "rel1", "self_user_id": "u1",
        "linked_user_id": "u2", "relation_type": "DOCTOR",
        "is_active": True,
    })
    assert rel["relation_type"] == "DOCTOR"

    link = await repo.find_active_link("u1", "u2")
    assert link is not None

    by_self = await repo.find_active_by_self_user("u1")
    assert len(by_self) >= 1


# ---------------------------------------------------------------
# Live status repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_status_upsert(db_session):
    from repositories.sqlite.repos import SqliteLiveStatusRepo
    from datetime import datetime
    repo = SqliteLiveStatusRepo(db_session)
    ls = await repo.upsert("u1", {
        "heart_rate": 75.0, "spo2": 98.0,
        "motion_score": 0.1, "risk_score": 0.05,
        "scenario": "normal", "timestamp": datetime.utcnow(),
    })
    assert ls["heart_rate"] == 75.0

    # Update existing
    ls2 = await repo.upsert("u1", {"heart_rate": 80.0})
    assert ls2["heart_rate"] == 80.0


# ---------------------------------------------------------------
# Anomaly repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_anomaly_create_and_list(db_session):
    from repositories.sqlite.repos import SqliteAnomalyRepo
    repo = SqliteAnomalyRepo(db_session)
    a = await repo.create({
        "id": "a1", "user_id": "u1",
        "metric": "Heart Rate", "value": 120.0,
        "unit": "bpm", "severity": "warning",
        "summary": "Elevated HR",
    })
    assert a["metric"] == "Heart Rate"

    items = await repo.list_by_user("u1")
    assert len(items) >= 1


# ---------------------------------------------------------------
# Alert repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_alert_create_and_get_active(db_session):
    from repositories.sqlite.repos import SqliteAlertRepo
    repo = SqliteAlertRepo(db_session)
    alert = await repo.create({
        "id": "al1", "user_id": "u1",
        "title": "Test Alert", "description": "Test",
        "severity": "warning", "status": "countdown",
        "countdown_total_sec": 30, "countdown_remaining_sec": 30,
        "recommendations": ["Stay calm"],
    })
    assert alert["title"] == "Test Alert"
    assert alert["recommendations"] == ["Stay calm"]

    active = await repo.get_active_by_user("u1")
    assert active is not None
    assert active["id"] == "al1"


@pytest.mark.asyncio
async def test_alert_update_status(db_session):
    from repositories.sqlite.repos import SqliteAlertRepo
    repo = SqliteAlertRepo(db_session)
    await repo.create({
        "id": "al2", "user_id": "u1",
        "title": "Alert 2", "description": "Desc",
        "severity": "critical", "status": "countdown",
        "countdown_total_sec": 30, "countdown_remaining_sec": 30,
    })
    updated = await repo.update("al2", {"status": "resolved"})
    assert updated["status"] == "resolved"


# ---------------------------------------------------------------
# Notification repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_create_and_mark_read(db_session):
    from repositories.sqlite.repos import SqliteNotificationRepo
    repo = SqliteNotificationRepo(db_session)
    n = await repo.create({
        "id": "n1", "recipient_id": "u1",
        "title": "Test Notif", "body": "Hello",
        "notification_type": "alert", "is_read": False,
    })
    assert n["is_read"] is False

    found = await repo.mark_read("n1", "u1")
    assert found is True

    items = await repo.list_by_recipient("u1")
    assert any(i["id"] == "n1" and i["is_read"] is True for i in items)


@pytest.mark.asyncio
async def test_notification_mark_all_read(db_session):
    from repositories.sqlite.repos import SqliteNotificationRepo
    repo = SqliteNotificationRepo(db_session)
    await repo.create({
        "id": "n2", "recipient_id": "u1",
        "title": "Notif 2", "body": "World",
        "notification_type": "info", "is_read": False,
    })
    count = await repo.mark_all_read("u1")
    assert count >= 1


# ---------------------------------------------------------------
# History repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_create_and_list(db_session):
    from repositories.sqlite.repos import SqliteHistoryRepo
    repo = SqliteHistoryRepo(db_session)
    h = await repo.create({
        "id": "h1", "user_id": "u1",
        "item_type": "alert", "title": "Alert resolved",
        "subtitle": "Details", "severity": "warning",
    })
    assert h["item_type"] == "alert"

    items = await repo.list_by_user("u1")
    assert len(items) >= 1


# ---------------------------------------------------------------
# Settings repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_get_or_create(db_session):
    from repositories.sqlite.repos import SqliteSettingsRepo
    repo = SqliteSettingsRepo(db_session)
    s = await repo.get_or_create("u1")
    assert s["notifications_enabled"] is True
    assert s["battery_mode"] == "balanced"


@pytest.mark.asyncio
async def test_settings_update(db_session):
    from repositories.sqlite.repos import SqliteSettingsRepo
    repo = SqliteSettingsRepo(db_session)
    await repo.get_or_create("u1")
    updated = await repo.update("u1", {"battery_mode": "power_save"})
    assert updated["battery_mode"] == "power_save"


# ---------------------------------------------------------------
# Clinical note repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_clinical_note_crud(db_session):
    from repositories.sqlite.repos import SqliteClinicalNoteRepo
    repo = SqliteClinicalNoteRepo(db_session)
    note = await repo.create({
        "id": "cn1", "doctor_id": "u2", "patient_id": "u1",
        "note": "Patient stable", "recommendation": "Continue meds",
    })
    assert note["note"] == "Patient stable"

    updated = await repo.update("cn1", {"note": "Updated note"})
    assert updated["note"] == "Updated note"

    by_patient = await repo.list_by_patient("u1")
    assert len(by_patient) >= 1

    deleted = await repo.delete("cn1")
    assert deleted is True

    gone = await repo.get_by_id("cn1")
    assert gone is None


# ---------------------------------------------------------------
# Device repo
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_register_and_get(db_session):
    from repositories.sqlite.repos import SqliteDeviceRepo
    repo = SqliteDeviceRepo(db_session)
    reg = await repo.register_device({
        "id": "dr1", "device_id": "ESP32-001",
        "user_id": "u1",
    })
    assert reg["device_id"] == "ESP32-001"

    fetched = await repo.get_registration("ESP32-001")
    assert fetched is not None
    assert fetched["user_id"] == "u1"


@pytest.mark.asyncio
async def test_device_log_packet(db_session):
    from repositories.sqlite.repos import SqliteDeviceRepo
    repo = SqliteDeviceRepo(db_session)
    log = await repo.log_packet({
        "id": "pl1", "device_id": "ESP32-001",
        "user_id": "u1", "timestamp_ms": 12345,
        "mode": "mock", "packet_seq": 1,
        "accel_x": 0.0, "accel_y": 0.0, "accel_z": 1.0,
        "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        "red_value": 1000, "ir_value": 2000,
        "heart_rate": 72.0, "spo2": 98.0,
        "signal_quality": 0.9,
        "imu_ok": True, "ppg_ok": True,
        "hr_valid": True, "spo2_valid": True,
        "finger_detected": True, "state_hint": "normal",
    })
    assert log["packet_seq"] == 1
