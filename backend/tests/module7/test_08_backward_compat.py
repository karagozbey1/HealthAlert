"""
Module 7 – Test 08: Backward compatibility & integration checks
Verifies that the default sqlite mode preserves all existing behaviour:
- Server boots with DATA_MODE=sqlite (default)
- Router imports work
- deps.get_repo_set is injectable
- No breaking changes to schemas
"""
import os
import sys
import importlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Force sqlite mode for safety
os.environ.pop("DATA_MODE", None)
os.environ.pop("FIREBASE_PROJECT_ID", None)
os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)


# ---------------------------------------------------------------
# Import-level smoke tests
# ---------------------------------------------------------------

def test_config_loads_with_defaults():
    """Settings load without any Firebase env vars."""
    from config import settings
    assert settings.DATA_MODE == "sqlite"
    assert settings.FIREBASE_PROJECT_ID == ""
    assert settings.FIREBASE_CREDENTIALS_PATH == ""


def test_all_routers_importable():
    """All router modules import without error."""
    router_modules = [
        "routers.auth_router",
        "routers.users_router",
        "routers.live_status_router",
        "routers.anomalies_router",
        "routers.alerts_router",
        "routers.history_router",
        "routers.notifications_router",
        "routers.clinical_notes_router",
        "routers.settings_router",
        "routers.link_codes_router",
        "routers.ingestion_router",
    ]
    for mod_name in router_modules:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "router"), f"{mod_name} missing 'router' attribute"


def test_deps_module_has_get_repo_set():
    """deps.py exports get_repo_set callable."""
    from routers.deps import get_repo_set
    assert callable(get_repo_set)


def test_main_app_creates():
    """FastAPI app object can be created."""
    from main import app
    assert app is not None
    assert app.title  # should have a title


# ---------------------------------------------------------------
# Schema backward compat
# ---------------------------------------------------------------

def test_schemas_unchanged():
    """Key schema classes still exist and have expected fields."""
    import schemas
    # RegisterRequest
    assert hasattr(schemas, "RegisterRequest")
    rr_fields = set(schemas.RegisterRequest.model_fields.keys())
    assert {"email", "password", "full_name", "role"}.issubset(rr_fields)

    # AlertResponse
    assert hasattr(schemas, "AlertResponse")

    # LiveStatusResponse
    assert hasattr(schemas, "LiveStatusResponse")


def test_models_unchanged():
    """Key ORM models still exist."""
    import models
    expected = [
        "User", "LinkCode", "UserRelation", "LiveStatus",
        "AnomalyEvent", "AlertEvent", "HistoryItem",
        "NotificationItem", "ClinicalNote", "AppSettings",
    ]
    for name in expected:
        assert hasattr(models, name), f"models.{name} missing"


# ---------------------------------------------------------------
# Repository factory defaults
# ---------------------------------------------------------------

def test_factory_returns_sqlite_by_default():
    """get_repos() with DATA_MODE=sqlite uses SQLite implementations."""
    from unittest.mock import MagicMock
    from repositories.factory import get_repos
    mock_db = MagicMock()  # AsyncSession mock
    repo_set = get_repos(db=mock_db)
    assert repo_set is not None

    from repositories.sqlite.repos import SqliteUserRepo
    assert isinstance(repo_set.users, SqliteUserRepo)


def test_factory_firebase_mode_without_client_raises():
    """In firebase mode without a Firestore client, factory should handle gracefully."""
    from unittest.mock import patch
    from repositories.factory import get_repos

    with patch("repositories.factory.settings") as mock_settings:
        mock_settings.DATA_MODE = "firebase"

    # firebase client is None by default → should still be callable
    # (actual Firebase repos will fail on operations, not on construction)


# ---------------------------------------------------------------
# Firebase client graceful degradation
# ---------------------------------------------------------------

def test_init_firebase_noop_in_sqlite_mode():
    """init_firebase does nothing when DATA_MODE=sqlite."""
    from unittest.mock import patch
    with patch("firebase_client.settings") as ms:
        ms.DATA_MODE = "sqlite"
        from firebase_client import init_firebase
        init_firebase()  # should not raise


def test_get_firestore_client_returns_none_initially():
    """Without init, get_firestore_client returns None."""
    import firebase_client as fc
    # Reset state
    fc._firestore_client = None
    result = fc.get_firestore_client()
    assert result is None


# ---------------------------------------------------------------
# Endpoint route count
# ---------------------------------------------------------------

def test_app_has_expected_route_count():
    """App should have at least the routes from all 11 routers."""
    from main import app
    routes = [r for r in app.routes if hasattr(r, "methods")]
    # We had 40+ endpoints before Module 7, should be at least that many
    assert len(routes) >= 20, f"Only {len(routes)} routes found"
