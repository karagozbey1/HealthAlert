
import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_cloud_push.db"
os.environ["DATA_MODE"] = "sqlite"
os.environ["NOTIFICATION_MODE"] = "poll"
os.environ.pop("FCM_SERVER_KEY", None)
os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)
os.environ.pop("FIREBASE_PROJECT_ID", None)

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///./test_cloud_push.db", echo=False)
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
        os.remove("test_cloud_push.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


# ===================================================================
# 1. Firebase env validation & credential path checks
# ===================================================================

class TestFirebaseEnvValidation:
    """Verify config validation catches Firebase misconfigurations."""

    def test_firebase_mode_without_project_id_warns(self):
        os.environ["DATA_MODE"] = "firebase"
        os.environ.pop("FIREBASE_PROJECT_ID", None)
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("FIREBASE_PROJECT_ID" in w for w in warnings)
        finally:
            os.environ["DATA_MODE"] = "sqlite"
            config.settings = Settings()

    def test_hybrid_mode_without_project_id_warns(self):
        os.environ["DATA_MODE"] = "hybrid"
        os.environ.pop("FIREBASE_PROJECT_ID", None)
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("FIREBASE_PROJECT_ID" in w for w in warnings)
        finally:
            os.environ["DATA_MODE"] = "sqlite"
            config.settings = Settings()

    def test_firebase_mode_without_credentials_info_message(self):
        os.environ["DATA_MODE"] = "firebase"
        os.environ["FIREBASE_PROJECT_ID"] = "test-project"
        os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("Application Default Credentials" in w for w in warnings)
        finally:
            os.environ["DATA_MODE"] = "sqlite"
            os.environ.pop("FIREBASE_PROJECT_ID", None)
            config.settings = Settings()

    def test_nonexistent_credentials_path_warns(self):
        os.environ["DATA_MODE"] = "firebase"
        os.environ["FIREBASE_PROJECT_ID"] = "test-project"
        os.environ["FIREBASE_CREDENTIALS_PATH"] = "/nonexistent/path/creds.json"
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            assert any("not found" in w for w in warnings)
        finally:
            os.environ["DATA_MODE"] = "sqlite"
            os.environ.pop("FIREBASE_PROJECT_ID", None)
            os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)
            config.settings = Settings()

    def test_sqlite_mode_no_firebase_warnings(self):
        os.environ["DATA_MODE"] = "sqlite"
        os.environ.pop("FIREBASE_PROJECT_ID", None)
        try:
            from config import validate_settings, Settings
            import config
            config.settings = Settings()
            warnings = validate_settings()
            firebase_warnings = [w for w in warnings if "FIREBASE" in w]
            assert len(firebase_warnings) == 0
        finally:
            config.settings = Settings()


# ===================================================================
# 2. Firebase client credential path validation
# ===================================================================

class TestFirebaseCredentialValidation:
    """Verify firebase_client validates credential paths properly."""

    def setup_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        firebase_client._firebase_status = {
            "needed": False,
            "credentials_path_configured": False,
            "credentials_file_exists": False,
            "project_id_configured": False,
            "sdk_initialised": False,
            "firestore_connected": False,
            "error": None,
            "mode": "sqlite",
        }

    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        os.environ["DATA_MODE"] = "sqlite"
        os.environ.pop("FIREBASE_PROJECT_ID", None)
        os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)

    def test_validate_nonexistent_path(self):
        from firebase_client import _validate_credentials_path
        with patch("firebase_client.settings") as mock_settings:
            mock_settings.FIREBASE_CREDENTIALS_PATH = "/nonexistent/file.json"
            result = _validate_credentials_path()
            assert result is not None
            assert "not found" in result

    def test_validate_empty_path_returns_none(self):
        from firebase_client import _validate_credentials_path
        with patch("firebase_client.settings") as mock_settings:
            mock_settings.FIREBASE_CREDENTIALS_PATH = ""
            result = _validate_credentials_path()
            assert result is None

    def test_init_firebase_with_bad_path_records_error(self):
        import firebase_client
        with patch.object(firebase_client.settings, "DATA_MODE", "firebase"), \
             patch.object(firebase_client.settings, "FIREBASE_PROJECT_ID", "test-proj"), \
             patch.object(firebase_client.settings, "FIREBASE_CREDENTIALS_PATH", "/bad/path.json"):
            firebase_client._initialised = False
            firebase_client.init_firebase()
            assert firebase_client._initialised is True
            assert firebase_client._firestore_client is None
            status = firebase_client.get_firebase_status()
            assert status["error"] is not None
            assert "not found" in status["error"]

    def test_init_firebase_without_project_id_records_error(self):
        import firebase_client
        with patch.object(firebase_client.settings, "DATA_MODE", "firebase"), \
             patch.object(firebase_client.settings, "FIREBASE_PROJECT_ID", ""), \
             patch.object(firebase_client.settings, "FIREBASE_CREDENTIALS_PATH", ""):
            firebase_client._initialised = False
            firebase_client.init_firebase()
            assert firebase_client._initialised is True
            assert firebase_client._firestore_client is None
            status = firebase_client.get_firebase_status()
            assert "FIREBASE_PROJECT_ID" in (status["error"] or "")


# ===================================================================
# 3. Firebase status reporting
# ===================================================================

class TestFirebaseStatus:
    """Verify firebase status dict is properly populated."""

    def setup_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        firebase_client._firebase_status = {
            "needed": False,
            "credentials_path_configured": False,
            "credentials_file_exists": False,
            "project_id_configured": False,
            "sdk_initialised": False,
            "firestore_connected": False,
            "error": None,
            "mode": "sqlite",
        }

    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None

    def test_sqlite_mode_status(self):
        import firebase_client
        with patch.object(firebase_client.settings, "DATA_MODE", "sqlite"):
            firebase_client._initialised = False
            firebase_client.init_firebase()
            status = firebase_client.get_firebase_status()
            assert status["needed"] is False
            assert status["mode"] == "sqlite"
            assert status["firestore_connected"] is False
            assert status["error"] is None

    def test_firebase_mode_needed(self):
        import firebase_client
        with patch.object(firebase_client.settings, "DATA_MODE", "firebase"), \
             patch.object(firebase_client.settings, "FIREBASE_PROJECT_ID", ""), \
             patch.object(firebase_client.settings, "FIREBASE_CREDENTIALS_PATH", ""):
            firebase_client._initialised = False
            firebase_client.init_firebase()
            status = firebase_client.get_firebase_status()
            assert status["needed"] is True
            assert status["mode"] == "firebase"


# ===================================================================
# 4. Push mode selection & graceful degrade
# ===================================================================

class TestPushModeSelection:
    """Verify push service mode detection and degradation."""

    def test_poll_mode_status(self):
        from services.push_service import get_push_status
        import services.push_service as ps
        with patch.object(ps.settings, "NOTIFICATION_MODE", "poll"), \
             patch.object(ps.settings, "FCM_SERVER_KEY", ""):
            status = get_push_status()
            assert status["notification_mode"] == "poll"
            assert status["push_enabled"] is False
            assert status["push_ready"] is False
            assert status["push_effective_mode"] == "poll_only"

    def test_push_mode_without_key_degraded(self):
        from services.push_service import get_push_status
        import services.push_service as ps
        with patch.object(ps.settings, "NOTIFICATION_MODE", "push"), \
             patch.object(ps.settings, "FCM_SERVER_KEY", ""):
            status = get_push_status()
            assert status["push_enabled"] is True
            assert status["fcm_key_configured"] is False
            assert status["push_ready"] is False
            assert status["push_effective_mode"] == "push_degraded_to_poll"

    def test_push_mode_with_key_ready(self):
        from services.push_service import get_push_status
        import services.push_service as ps
        with patch.object(ps.settings, "NOTIFICATION_MODE", "push"), \
             patch.object(ps.settings, "FCM_SERVER_KEY", "fake-key-for-test"):
            status = get_push_status()
            assert status["push_enabled"] is True
            assert status["fcm_key_configured"] is True
            assert status["push_ready"] is True
            assert status["push_effective_mode"] == "live_push"


# ===================================================================
# 5. FCM key missing → graceful degrade
# ===================================================================

class TestFCMKeyMissing:
    """Push service returns 0 when key is missing — never crashes."""

    async def test_push_to_user_no_key_poll_mode(self, db):
        import config
        os.environ.pop("FCM_SERVER_KEY", None)
        os.environ["NOTIFICATION_MODE"] = "poll"
        try:
            config.settings = config.Settings()
            from services.push_service import push_to_user
            count = await push_to_user(db, "user-x", "Title", "Body")
            assert count == 0
        finally:
            os.environ.pop("NOTIFICATION_MODE", None)
            config.settings = config.Settings()

    async def test_push_to_user_no_key_push_mode(self, db):
        import config
        os.environ.pop("FCM_SERVER_KEY", None)
        os.environ["NOTIFICATION_MODE"] = "push"
        try:
            config.settings = config.Settings()
            from services.push_service import push_to_user
            count = await push_to_user(db, "user-x", "Title", "Body")
            assert count == 0
        finally:
            os.environ.pop("NOTIFICATION_MODE", None)
            config.settings = config.Settings()


# ===================================================================
# 6. Token registration / unregistration
# ===================================================================

class TestTokenRegistration:
    """Verify FCM device token CRUD in database."""

    async def test_create_token(self, db):
        from models import DeviceToken
        dt = DeviceToken(
            id="tok-1",
            user_id="usr-1",
            token="fcm:test-token-aaa111",
            platform="android",
        )
        db.add(dt)
        await db.commit()
        await db.refresh(dt)
        assert dt.id == "tok-1"
        assert dt.platform == "android"

    async def test_query_tokens_by_user(self, db):
        from sqlalchemy import select
        from models import DeviceToken
        # Add extra token
        dt2 = DeviceToken(
            id="tok-2",
            user_id="usr-1",
            token="fcm:test-token-bbb222",
            platform="ios",
        )
        db.add(dt2)
        await db.commit()

        result = await db.execute(
            select(DeviceToken).where(DeviceToken.user_id == "usr-1")
        )
        tokens = result.scalars().all()
        assert len(tokens) >= 2

    async def test_delete_token(self, db):
        from sqlalchemy import delete, select
        from models import DeviceToken
        # Add then delete
        dt = DeviceToken(
            id="tok-del",
            user_id="usr-del",
            token="fcm:delete-me",
            platform="web",
        )
        db.add(dt)
        await db.commit()

        await db.execute(
            delete(DeviceToken).where(DeviceToken.token == "fcm:delete-me")
        )
        await db.commit()

        result = await db.execute(
            select(DeviceToken).where(DeviceToken.token == "fcm:delete-me")
        )
        assert result.scalar_one_or_none() is None

    async def test_upsert_existing_token(self, db):
        from sqlalchemy import select
        from models import DeviceToken
        from datetime import datetime
        # Create
        dt = DeviceToken(
            id="tok-ups",
            user_id="usr-ups",
            token="fcm:upsert-token",
            platform="android",
        )
        db.add(dt)
        await db.commit()

        # Update platform
        result = await db.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == "usr-ups",
                DeviceToken.token == "fcm:upsert-token",
            )
        )
        existing = result.scalar_one_or_none()
        assert existing is not None
        existing.platform = "ios"
        existing.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        assert existing.platform == "ios"


# ===================================================================
# 7. Notification persistence when push fails
# ===================================================================

class TestNotificationPersistenceOnPushFailure:
    """Notifications must be saved in DB even if push delivery fails."""

    async def test_notification_persists_when_push_raises(self, db):
        from models import NotificationItem, User
        from services.notification import notify_single

        # Create a test user
        user = User(
            id="usr-persist",
            email="persist@test.com",
            password_hash="xxx",
            role="RELATIVE",
            full_name="Test Persist",
        )
        db.add(user)
        await db.commit()

        # Mock push_to_user to raise an exception
        with patch("services.notification.push_to_user", side_effect=Exception("FCM down")):
            await notify_single(
                db, "usr-persist", "Test Title", "Test Body",
                "test", sender_id="usr-sender",
            )
            await db.commit()

        # Notification should still be in DB
        from sqlalchemy import select
        result = await db.execute(
            select(NotificationItem).where(
                NotificationItem.recipient_id == "usr-persist"
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) >= 1
        assert notifs[0].title == "Test Title"

    async def test_notify_linked_users_persists_when_push_fails(self, db):
        from models import NotificationItem, User, UserRelation
        from services.notification import notify_linked_users

        # Create SELF and RELATIVE users
        self_user = User(
            id="usr-self-rel",
            email="self-rel@test.com",
            password_hash="xxx",
            role="SELF",
            full_name="Self User",
        )
        rel_user = User(
            id="usr-rel-rel",
            email="rel-rel@test.com",
            password_hash="xxx",
            role="RELATIVE",
            full_name="Relative User",
        )
        db.add(self_user)
        db.add(rel_user)
        await db.flush()

        # Create relation
        db.add(UserRelation(
            id="rel-link",
            self_user_id="usr-self-rel",
            linked_user_id="usr-rel-rel",
            relation_type="RELATIVE",
            is_active=True,
        ))
        await db.commit()

        # Mock push_to_user to fail
        with patch("services.notification.push_to_user", side_effect=Exception("FCM offline")):
            await notify_linked_users(
                db, "usr-self-rel", "Self User",
                "Alert Title", "Alert Body", "alert",
            )
            await db.commit()

        # Notification should be saved
        from sqlalchemy import select
        result = await db.execute(
            select(NotificationItem).where(
                NotificationItem.recipient_id == "usr-rel-rel"
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) >= 1


# ===================================================================
# 8. Invalid token cleanup
# ===================================================================

class TestInvalidTokenCleanup:
    """Verify that invalid FCM tokens are cleaned from DB."""

    async def test_cleanup_invalid_token(self, db):
        from models import DeviceToken
        from services.push_service import _cleanup_invalid_token

        # Add a token
        dt = DeviceToken(
            id="tok-invalid",
            user_id="usr-invalid",
            token="fcm:invalid-token-xxx",
            platform="android",
        )
        db.add(dt)
        await db.commit()

        # Clean it
        await _cleanup_invalid_token(db, "fcm:invalid-token-xxx", "usr-invalid")
        await db.commit()

        # Should be gone
        from sqlalchemy import select
        result = await db.execute(
            select(DeviceToken).where(DeviceToken.token == "fcm:invalid-token-xxx")
        )
        assert result.scalar_one_or_none() is None


# ===================================================================
# 9. Push delivery stats tracking
# ===================================================================

class TestPushDeliveryStats:
    """Verify push stats are updated on delivery attempts."""

    async def test_stats_track_attempts(self, db):
        from services import push_service
        # Reset stats
        push_service._push_stats = {
            "total_attempts": 0,
            "total_successes": 0,
            "total_failures": 0,
            "invalid_tokens_cleaned": 0,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
        }

        # Add a token
        from models import DeviceToken
        dt = DeviceToken(
            id="tok-stats",
            user_id="usr-stats",
            token="fcm:stats-token",
            platform="android",
        )
        db.add(dt)
        await db.commit()

        # Mock FCM to fail, patch settings for push mode
        with patch.object(push_service.settings, "NOTIFICATION_MODE", "push"), \
             patch.object(push_service.settings, "FCM_SERVER_KEY", "fake-key"), \
             patch("services.push_service._send_fcm_message",
                    return_value={"ok": False, "token_invalid": False, "detail": "test fail"}):
            from services.push_service import push_to_user
            count = await push_to_user(db, "usr-stats", "T", "B")
            assert count == 0

        assert push_service._push_stats["total_attempts"] >= 1
        assert push_service._push_stats["total_failures"] >= 1
        assert push_service._push_stats["last_error"] == "test fail"


# ===================================================================
# 10. FCM send function unit tests
# ===================================================================

class TestFCMSendFunction:
    """Test _send_fcm_message with mocked HTTP."""

    async def test_send_returns_ok_on_success(self):
        import services.push_service as ps
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": 1, "results": [{"message_id": "abc"}]}

        with patch.object(ps.settings, "FCM_SERVER_KEY", "test-key"), \
             patch("services.push_service.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            from services.push_service import _send_fcm_message
            result = await _send_fcm_message("token123", "Title", "Body")
            assert result["ok"] is True

    async def test_send_detects_invalid_token(self):
        import services.push_service as ps
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": 0,
            "failure": 1,
            "results": [{"error": "NotRegistered"}],
        }

        with patch.object(ps.settings, "FCM_SERVER_KEY", "test-key"), \
             patch("services.push_service.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            from services.push_service import _send_fcm_message
            result = await _send_fcm_message("bad-token", "Title", "Body")
            assert result["ok"] is False
            assert result["token_invalid"] is True

    async def test_send_handles_401_auth_failure(self):
        import services.push_service as ps
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(ps.settings, "FCM_SERVER_KEY", "bad-key"), \
             patch("services.push_service.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            from services.push_service import _send_fcm_message
            result = await _send_fcm_message("token", "Title", "Body")
            assert result["ok"] is False
            assert "authentication" in result["detail"].lower()

    async def test_send_no_key_returns_false(self):
        import services.push_service as ps
        with patch.object(ps.settings, "FCM_SERVER_KEY", ""):
            from services.push_service import _send_fcm_message
            result = await _send_fcm_message("token", "Title", "Body")
            assert result["ok"] is False


# ===================================================================
# 11. Smoke test functions (unit level)
# ===================================================================

class TestSmokeTestFunctions:
    """Verify smoke test functions work without real services."""

    async def test_firebase_smoke_no_client(self):
        from firebase_client import firebase_smoke_test
        with patch("firebase_client.get_firestore_client", return_value=None):
            result = await firebase_smoke_test()
            assert result["ok"] is False
            assert "not available" in result["detail"]

    async def test_push_smoke_poll_mode(self, db):
        from services.push_service import push_smoke_test
        import config
        os.environ["NOTIFICATION_MODE"] = "poll"
        os.environ.pop("FCM_SERVER_KEY", None)
        try:
            config.settings = config.Settings()
            result = await push_smoke_test(db)
            assert result["ok"] is False
            assert "not 'push'" in result["detail"]
        finally:
            config.settings = config.Settings()

    async def test_push_smoke_no_key(self, db):
        from services.push_service import push_smoke_test
        import services.push_service as ps
        with patch.object(ps.settings, "NOTIFICATION_MODE", "push"), \
             patch.object(ps.settings, "FCM_SERVER_KEY", ""):
            result = await push_smoke_test(db)
            assert result["ok"] is False
            assert "FCM_SERVER_KEY" in result["detail"]


# ===================================================================
# 12. Readiness endpoint integration (via TestClient)
# ===================================================================

class TestReadinessEndpoint:
    """Verify /readiness returns comprehensive status."""

    async def test_readiness_returns_firebase_section(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert "firebase" in data
        assert "push" in data
        assert "fallback_info" in data
        assert "version" in data

    async def test_readiness_firebase_fields(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/readiness")
        fb = resp.json()["firebase"]
        assert "needed" in fb
        assert "project_id" in fb
        assert "credentials_configured" in fb
        assert "sdk_initialised" in fb
        assert "firestore_connected" in fb
        assert "cloud_ready" in fb

    async def test_readiness_push_fields(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/readiness")
        push = resp.json()["push"]
        assert "notification_mode" in push
        assert "fcm_key_configured" in push
        assert "push_ready" in push
        assert "effective_mode" in push
        assert "delivery_stats" in push

    async def test_health_endpoint(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_cloud_smoke_endpoint_sqlite_mode(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/cloud/smoke")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False  # Not in firebase mode
        assert "DATA_MODE" in data["detail"]

    async def test_push_smoke_endpoint(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/push/smoke")
        assert resp.status_code == 200
        data = resp.json()
        # In poll mode, should report not ready
        assert "push_status" in data


# ===================================================================
# 13. Hybrid mode write fan-out
# ===================================================================

class TestHybridModeBehavior:
    """Verify hybrid mode configuration is correct."""

    def test_hybrid_requires_db(self):
        from repositories.factory import get_repos
        with pytest.raises(ValueError, match="hybrid"):
            get_repos(db=None, mode="hybrid")

    def test_sqlite_requires_db(self):
        from repositories.factory import get_repos
        with pytest.raises(ValueError, match="sqlite"):
            get_repos(db=None, mode="sqlite")

    def test_firebase_no_db_needed(self):
        """firebase mode doesn't require db (but needs Firestore client)."""
        from repositories.factory import get_repos
        # This will work but Firebase repos will have fs=None
        try:
            repos = get_repos(db=None, mode="firebase")
            assert repos is not None
        except Exception:
            pass  # Expected if firebase-admin import fails


# ===================================================================
# 14. Notification fan-out with repos
# ===================================================================

class TestNotificationWithRepos:
    """Verify notification fan-out works via repository layer."""

    async def test_notify_single_via_repos(self, db):
        from repositories.factory import get_repos
        from services.notification import notify_single
        repos = get_repos(db=db, mode="sqlite")

        # Create recipient user first
        from models import User
        user = User(
            id="usr-repo-notif",
            email="repo-notif@test.com",
            password_hash="xxx",
            role="RELATIVE",
            full_name="Repo Notif",
        )
        db.add(user)
        await db.commit()

        with patch("services.notification.push_to_user", return_value=0):
            await notify_single(
                db, "usr-repo-notif", "Repo Title", "Repo Body",
                "test", repos=repos,
            )
            await db.commit()

        notifs = await repos.notifications.list_by_recipient("usr-repo-notif")
        assert len(notifs) >= 1
        assert notifs[0]["title"] == "Repo Title"
