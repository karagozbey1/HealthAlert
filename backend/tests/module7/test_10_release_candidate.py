"""
Release Candidate Tests — config modes, push notification infrastructure,
duplicate packet detection, readiness endpoint.

These tests validate the new features added in the final release sprint.
"""
import os
import sys
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_rc.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///./test_rc.db", echo=False)
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
    try:
        os.remove("test_rc.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


# ===================================================================
# Config Mode Tests
# ===================================================================

class TestConfigModes:
    """Verify unified config mode system works correctly."""

    def test_default_app_mode_is_demo(self):
        from config import Settings
        s = Settings()
        assert s.APP_MODE == "demo"

    def test_sensor_mode_default_auto(self):
        from config import Settings
        s = Settings()
        assert s.SENSOR_MODE == "auto"

    def test_ai_mode_default_mock(self):
        from config import Settings
        s = Settings()
        assert s.AI_MODE == "mock"

    def test_notification_mode_default_poll(self):
        from config import Settings
        s = Settings()
        assert s.NOTIFICATION_MODE == "poll"

    def test_simulation_enabled_default_auto(self):
        from config import Settings
        s = Settings()
        assert s.SIMULATION_ENABLED == "auto"

    def test_fcm_server_key_default_empty(self):
        from config import Settings
        s = Settings()
        assert s.FCM_SERVER_KEY == ""


class TestShouldRunSimulation:
    """Verify simulation decision logic."""

    def test_simulation_on_always_runs(self):
        os.environ["SIMULATION_ENABLED"] = "on"
        try:
            from config import should_run_simulation, Settings
            # Re-create settings with new env
            import config
            config.settings = Settings()
            assert should_run_simulation() is True
        finally:
            os.environ.pop("SIMULATION_ENABLED", None)
            config.settings = Settings()

    def test_simulation_off_never_runs(self):
        os.environ["SIMULATION_ENABLED"] = "off"
        try:
            from config import should_run_simulation, Settings
            import config
            config.settings = Settings()
            assert should_run_simulation() is False
        finally:
            os.environ.pop("SIMULATION_ENABLED", None)
            config.settings = Settings()

    def test_simulation_auto_demo_mock_runs(self):
        os.environ["SIMULATION_ENABLED"] = "auto"
        os.environ["APP_MODE"] = "demo"
        os.environ["SENSOR_MODE"] = "mock"
        try:
            from config import should_run_simulation, Settings
            import config
            config.settings = Settings()
            assert should_run_simulation() is True
        finally:
            for k in ["SIMULATION_ENABLED", "APP_MODE", "SENSOR_MODE"]:
                os.environ.pop(k, None)
            config.settings = Settings()

    def test_simulation_auto_production_doesnt_run(self):
        os.environ["SIMULATION_ENABLED"] = "auto"
        os.environ["APP_MODE"] = "production"
        try:
            from config import should_run_simulation, Settings
            import config
            config.settings = Settings()
            assert should_run_simulation() is False
        finally:
            for k in ["SIMULATION_ENABLED", "APP_MODE"]:
                os.environ.pop(k, None)
            config.settings = Settings()


class TestValidateSettings:
    """Verify config validation warnings."""

    def test_production_with_demo_secret_warns(self):
        os.environ["APP_MODE"] = "production"
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("SECRET_KEY" in w for w in warnings)
        finally:
            os.environ.pop("APP_MODE", None)
            config.settings = Settings()

    def test_push_without_fcm_warns(self):
        os.environ["NOTIFICATION_MODE"] = "push"
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("FCM_SERVER_KEY" in w for w in warnings)
        finally:
            os.environ.pop("NOTIFICATION_MODE", None)
            config.settings = Settings()


# ===================================================================
# DeviceToken model tests
# ===================================================================

class TestDeviceTokenModel:
    """Verify DeviceToken ORM model works in SQLite."""

    async def test_create_device_token(self, db):
        from models import DeviceToken
        dt = DeviceToken(
            id="dt-1",
            user_id="user-1",
            token="fcm-token-abc123",
            platform="android",
        )
        db.add(dt)
        await db.commit()
        await db.refresh(dt)
        assert dt.id == "dt-1"
        assert dt.platform == "android"
        assert dt.token == "fcm-token-abc123"
        assert dt.created_at is not None

    async def test_query_device_tokens_by_user(self, db):
        from sqlalchemy import select
        from models import DeviceToken
        # Add a second token
        dt2 = DeviceToken(
            id="dt-2",
            user_id="user-1",
            token="fcm-token-def456",
            platform="ios",
        )
        db.add(dt2)
        await db.commit()

        result = await db.execute(
            select(DeviceToken).where(DeviceToken.user_id == "user-1")
        )
        tokens = result.scalars().all()
        assert len(tokens) >= 2


# ===================================================================
# Duplicate packet detection tests
# ===================================================================

class TestDuplicateDetection:
    """Verify in-memory dedup LRU in ingestion router."""

    def test_first_packet_not_duplicate(self):
        from routers.ingestion_router import _is_duplicate, _seen_packets
        _seen_packets.clear()
        assert _is_duplicate("dev-test", 1) is False

    def test_same_packet_is_duplicate(self):
        from routers.ingestion_router import _is_duplicate, _seen_packets
        _seen_packets.clear()
        _is_duplicate("dev-test", 100)
        assert _is_duplicate("dev-test", 100) is True

    def test_different_seq_not_duplicate(self):
        from routers.ingestion_router import _is_duplicate, _seen_packets
        _seen_packets.clear()
        _is_duplicate("dev-test", 200)
        assert _is_duplicate("dev-test", 201) is False

    def test_different_device_not_duplicate(self):
        from routers.ingestion_router import _is_duplicate, _seen_packets
        _seen_packets.clear()
        _is_duplicate("dev-A", 300)
        assert _is_duplicate("dev-B", 300) is False

    def test_lru_eviction(self):
        from routers.ingestion_router import _is_duplicate, _seen_packets, _DEDUP_MAX
        _seen_packets.clear()
        # Fill beyond max
        for i in range(_DEDUP_MAX + 100):
            _is_duplicate("evict-dev", i)
        # First entries should have been evicted
        assert _is_duplicate("evict-dev", 0) is False
        # Recent entries should still be present
        assert _is_duplicate("evict-dev", _DEDUP_MAX + 50) is True
        _seen_packets.clear()


# ===================================================================
# Push service tests (unit — no real FCM)
# ===================================================================

class TestPushService:
    """Verify push_service graceful behavior without FCM credentials."""

    async def test_push_to_user_returns_zero_in_poll_mode(self, db):
        import config
        original = config.settings.NOTIFICATION_MODE
        # Ensure poll mode
        try:
            config.settings = config.Settings()
            from services.push_service import push_to_user
            count = await push_to_user(db, "user-1", "Test", "Body")
            assert count == 0
        finally:
            config.settings = config.Settings()

    async def test_push_to_user_no_tokens_returns_zero(self, db):
        """Even in push mode, if user has no tokens, returns 0."""
        import config
        os.environ["NOTIFICATION_MODE"] = "push"
        os.environ["FCM_SERVER_KEY"] = "fake-key-for-test"
        try:
            config.settings = config.Settings()
            from services.push_service import push_to_user
            count = await push_to_user(db, "nonexistent-user", "Test", "Body")
            assert count == 0
        finally:
            os.environ.pop("NOTIFICATION_MODE", None)
            os.environ.pop("FCM_SERVER_KEY", None)
            config.settings = config.Settings()


# ===================================================================
# Startup config log test
# ===================================================================

class TestStartupLog:
    """Verify log_startup_config runs without error."""

    def test_log_startup_config_doesnt_crash(self):
        from config import log_startup_config
        # Should not raise
        log_startup_config()


# ===================================================================
# Physiological bounds clamping tests
# ===================================================================

class TestPhysiologicalClamping:
    """Verify risk/motion score computations handle edge cases."""

    def test_motion_score_extreme_values(self):
        from routers.ingestion_router import _compute_motion_score
        score = _compute_motion_score(100.0, 100.0, 100.0, 1000.0, 1000.0, 1000.0)
        assert 0.0 <= score <= 1.0

    def test_motion_score_zero_values(self):
        from routers.ingestion_router import _compute_motion_score
        score = _compute_motion_score(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert 0.0 <= score <= 1.0

    def test_risk_score_bounds(self):
        from routers.ingestion_router import _compute_risk_score
        # Extreme high risk
        score = _compute_risk_score(200.0, 70.0, True, True, 1.0)
        assert 0.0 <= score <= 1.0

    def test_risk_score_normal(self):
        from routers.ingestion_router import _compute_risk_score
        score = _compute_risk_score(72.0, 98.0, True, True, 0.0)
        assert score == 0.0
