"""
Test 16 – Baseline MVP: Personal Baseline + Quality-aware Heuristic Risk

Tests:
 - Baseline yokken sistem global risk ile çalışır.
 - Güvenilir paket sample_count artırır.
 - signal_quality düşükse baseline güncellenmez.
 - finger_detected=false baseline güncellenmez.
 - mode=mock ve BASELINE_ALLOW_MOCK_DATA=false ise baseline güncellenmez.
 - baseline_ready=false iken final risk global riske yakın kalır.
 - baseline_ready=true ve HR kişisel ortalamadan çok saparsa final risk artar.
 - SpO2 kişisel ortalamadan düşerse risk artar.
 - response eski client'ı kırmaz (risk_breakdown opsiyonel).
 - DATA_MODE sqlite çalışır (SqliteBaselineRepo).
 - Hybrid mode import kırılmaz.
 - apply_baseline_adjustment sensitivity ile doğru davranır.
"""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_baseline.db")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///./test_baseline.db", echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

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
        os.remove("test_baseline.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db_session(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_repo_user(db_session, user_id: str = "baseline_user_1"):
    """Create a user and return the SqliteBaselineRepo for that session."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo
    return SqliteBaselineRepo(db_session), SqliteUserRepo(db_session), user_id


# ===========================================================================
# 1. SqliteBaselineRepo basic CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_baseline_get_or_create(db_session):
    """get_or_create creates a new row when no baseline exists yet."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu1", "email": "bu1@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU One",
    })

    repo = SqliteBaselineRepo(db_session)
    baseline = await repo.get_or_create("bu1")

    assert baseline["user_id"] == "bu1"
    assert baseline["sample_count"] == 0
    assert baseline["is_ready"] is False
    assert baseline["hr_mean"] == pytest.approx(72.0)
    assert baseline["spo2_mean"] == pytest.approx(98.0)


@pytest.mark.asyncio
async def test_baseline_get_or_create_idempotent(db_session):
    """Calling get_or_create twice returns the same baseline."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu2", "email": "bu2@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU Two",
    })

    repo = SqliteBaselineRepo(db_session)
    b1 = await repo.get_or_create("bu2")
    b2 = await repo.get_or_create("bu2")
    assert b1["id"] == b2["id"]


@pytest.mark.asyncio
async def test_baseline_update_values(db_session):
    """update_values correctly persists new sample_count and hr_mean."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu3", "email": "bu3@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU Three",
    })

    repo = SqliteBaselineRepo(db_session)
    await repo.get_or_create("bu3")

    updated = await repo.update_values("bu3", {"sample_count": 10, "hr_mean": 75.5, "is_ready": False})
    assert updated["sample_count"] == 10
    assert updated["hr_mean"] == pytest.approx(75.5)


# ===========================================================================
# 2. is_reliable_for_baseline gate tests
# ===========================================================================

def _default_reliable_kwargs(**overrides):
    base = dict(
        packet_mode="real",
        finger_detected=True,
        hr_valid=True,
        spo2_valid=True,
        signal_quality=0.80,
        ppg_ok=True,
        imu_ok=True,
        hr=72.0,
        spo2=98.0,
        global_risk_score=0.10,
    )
    base.update(overrides)
    return base


def test_reliable_normal():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs()) is True


def test_unreliable_finger_not_detected():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(finger_detected=False)) is False


def test_unreliable_low_signal_quality():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(signal_quality=0.40)) is False


def test_unreliable_hr_invalid():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(hr_valid=False)) is False


def test_unreliable_spo2_invalid():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(spo2_valid=False)) is False


def test_unreliable_ppg_not_ok():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(ppg_ok=False)) is False


def test_unreliable_mock_data_default():
    """mode=mock with BASELINE_ALLOW_MOCK_DATA=False → unreliable."""
    import services.baseline_service as bs
    original = bs.settings.BASELINE_ALLOW_MOCK_DATA
    try:
        bs.settings.BASELINE_ALLOW_MOCK_DATA = False
        result = bs.is_reliable_for_baseline(**_default_reliable_kwargs(packet_mode="mock"))
        assert result is False
    finally:
        bs.settings.BASELINE_ALLOW_MOCK_DATA = original


def test_reliable_mock_data_when_allowed():
    """mode=mock with BASELINE_ALLOW_MOCK_DATA=True → reliable (if other gates pass)."""
    import services.baseline_service as bs
    original = bs.settings.BASELINE_ALLOW_MOCK_DATA
    try:
        bs.settings.BASELINE_ALLOW_MOCK_DATA = True
        result = bs.is_reliable_for_baseline(**_default_reliable_kwargs(packet_mode="mock"))
        assert result is True
    finally:
        bs.settings.BASELINE_ALLOW_MOCK_DATA = original


def test_unreliable_high_risk():
    from services.baseline_service import is_reliable_for_baseline
    # global_risk_score >= WARNING_THRESHOLD (0.55) should block baseline update
    assert is_reliable_for_baseline(**_default_reliable_kwargs(global_risk_score=0.60)) is False


def test_unreliable_hr_out_of_range():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(hr=30.0)) is False
    assert is_reliable_for_baseline(**_default_reliable_kwargs(hr=200.0)) is False


def test_unreliable_spo2_out_of_range():
    from services.baseline_service import is_reliable_for_baseline
    assert is_reliable_for_baseline(**_default_reliable_kwargs(spo2=65.0)) is False


# ===========================================================================
# 3. update_user_baseline – incremental sample count
# ===========================================================================

@pytest.mark.asyncio
async def test_update_baseline_increments_sample_count(db_session):
    """A reliable packet should increment sample_count."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo
    from services.baseline_service import update_user_baseline

    class MockRepos:
        def __init__(self, session):
            self.baselines = SqliteBaselineRepo(session)

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu4", "email": "bu4@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU Four",
    })

    repos = MockRepos(db_session)
    result = await update_user_baseline(
        repos=repos,
        user_id="bu4",
        packet_mode="real",
        finger_detected=True,
        hr_valid=True,
        spo2_valid=True,
        signal_quality=0.85,
        ppg_ok=True,
        imu_ok=True,
        hr=70.0,
        spo2=98.0,
        motion_score=0.1,
        global_risk_score=0.05,
    )
    assert result["sample_count"] == 1


@pytest.mark.asyncio
async def test_update_baseline_not_incremented_on_low_quality(db_session):
    """A low signal_quality packet must NOT increment sample_count."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo
    from services.baseline_service import update_user_baseline

    class MockRepos:
        def __init__(self, session):
            self.baselines = SqliteBaselineRepo(session)

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu5", "email": "bu5@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU Five",
    })

    repos = MockRepos(db_session)
    # seed the baseline first
    await repos.baselines.get_or_create("bu5")

    result = await update_user_baseline(
        repos=repos,
        user_id="bu5",
        packet_mode="real",
        finger_detected=True,
        hr_valid=True,
        spo2_valid=True,
        signal_quality=0.30,   # < 0.50 threshold
        ppg_ok=True,
        imu_ok=True,
        hr=70.0,
        spo2=98.0,
        motion_score=0.1,
        global_risk_score=0.05,
    )
    assert result["sample_count"] == 0


@pytest.mark.asyncio
async def test_update_baseline_not_incremented_finger_not_detected(db_session):
    """finger_detected=False must NOT increment sample_count."""
    from repositories.sqlite.repos import SqliteBaselineRepo, SqliteUserRepo
    from services.baseline_service import update_user_baseline

    class MockRepos:
        def __init__(self, session):
            self.baselines = SqliteBaselineRepo(session)

    user_repo = SqliteUserRepo(db_session)
    await user_repo.create({
        "id": "bu6", "email": "bu6@test.com",
        "password_hash": "x", "role": "SELF", "full_name": "BU Six",
    })

    repos = MockRepos(db_session)
    await repos.baselines.get_or_create("bu6")

    result = await update_user_baseline(
        repos=repos,
        user_id="bu6",
        packet_mode="real",
        finger_detected=False,
        hr_valid=True,
        spo2_valid=True,
        signal_quality=0.90,
        ppg_ok=True,
        imu_ok=True,
        hr=70.0,
        spo2=98.0,
        motion_score=0.1,
        global_risk_score=0.05,
    )
    assert result["sample_count"] == 0


# ===========================================================================
# 4. compute_personal_deviation
# ===========================================================================

def test_deviation_normal_range():
    """No deviation for values within 2 std of mean."""
    from services.baseline_service import compute_personal_deviation

    baseline = {
        "hr_mean": 72.0, "hr_std": 10.0,
        "spo2_mean": 98.0, "spo2_std": 1.5,
        "motion_mean": 0.10, "motion_std": 0.08,
    }
    dev = compute_personal_deviation(
        baseline=baseline, hr=75.0, spo2=97.5, motion_score=0.15,
        hr_valid=True, spo2_valid=True,
    )
    assert dev["deviation_bonus"] == pytest.approx(0.0, abs=0.01)


def test_deviation_high_hr():
    """High HR significantly above mean should produce non-zero bonus."""
    from services.baseline_service import compute_personal_deviation

    baseline = {
        "hr_mean": 72.0, "hr_std": 10.0,
        "spo2_mean": 98.0, "spo2_std": 1.5,
        "motion_mean": 0.10, "motion_std": 0.08,
    }
    dev = compute_personal_deviation(
        baseline=baseline, hr=130.0, spo2=98.0, motion_score=0.10,
        hr_valid=True, spo2_valid=True,
    )
    # hr_z = (130 - 72) / 10 = 5.8 → contrib = (5.8 - 2) * 0.04 = 0.152
    assert dev["deviation_bonus"] > 0.0
    assert dev["hr_z"] == pytest.approx(5.8, abs=0.1)


def test_deviation_low_spo2():
    """SpO2 below personal mean should produce non-zero bonus."""
    from services.baseline_service import compute_personal_deviation

    baseline = {
        "hr_mean": 72.0, "hr_std": 10.0,
        "spo2_mean": 98.0, "spo2_std": 1.5,
        "motion_mean": 0.10, "motion_std": 0.08,
    }
    dev = compute_personal_deviation(
        baseline=baseline, hr=72.0, spo2=90.0, motion_score=0.10,
        hr_valid=True, spo2_valid=True,
    )
    # spo2_z = (98.0 - 90.0) / 1.5 = 5.33 → contrib = (5.33 - 2) * 0.06 = 0.20
    assert dev["deviation_bonus"] > 0.0
    assert dev["spo2_z"] > 2.0


def test_deviation_bonus_capped():
    """deviation_bonus must never exceed BASELINE_PERSONAL_BONUS_MAX."""
    from services.baseline_service import compute_personal_deviation
    import services.baseline_service as bs

    baseline = {
        "hr_mean": 72.0, "hr_std": 5.0,
        "spo2_mean": 98.0, "spo2_std": 1.0,
        "motion_mean": 0.10, "motion_std": 0.05,
    }
    dev = compute_personal_deviation(
        baseline=baseline, hr=200.0, spo2=60.0, motion_score=2.0,
        hr_valid=True, spo2_valid=True,
    )
    assert dev["deviation_bonus"] <= bs.settings.BASELINE_PERSONAL_BONUS_MAX + 0.001


# ===========================================================================
# 5. compute_quality_confidence
# ===========================================================================

def test_quality_confidence_full():
    from services.baseline_service import compute_quality_confidence
    info = compute_quality_confidence(
        signal_quality=0.9, finger_detected=True, hr_valid=True,
        spo2_valid=True, ppg_ok=True, spo2=98.0, spo2_valid_flag=True,
    )
    assert info["quality_confidence"] == pytest.approx(0.9, abs=0.01)
    assert info["quality_warning"] is None


def test_quality_confidence_no_finger():
    from services.baseline_service import compute_quality_confidence
    info = compute_quality_confidence(
        signal_quality=0.9, finger_detected=False, hr_valid=True,
        spo2_valid=True, ppg_ok=True, spo2=98.0, spo2_valid_flag=True,
    )
    assert info["quality_confidence"] == pytest.approx(0.0, abs=0.01)
    assert info["quality_warning"] is not None


def test_quality_confidence_safety_override_low_spo2():
    """safety_override should be True when SpO2 < 88 and valid."""
    from services.baseline_service import compute_quality_confidence
    info = compute_quality_confidence(
        signal_quality=0.3, finger_detected=True, hr_valid=True,
        spo2_valid=True, ppg_ok=True, spo2=84.0, spo2_valid_flag=True,
    )
    assert info["safety_override"] is True


# ===========================================================================
# 6. apply_baseline_adjustment
# ===========================================================================

def test_apply_adjustment_baseline_not_ready():
    """When baseline is not ready, final_risk_score == global_risk_score."""
    from services.baseline_service import apply_baseline_adjustment

    quality_info = {"quality_confidence": 0.9, "quality_warning": None, "safety_override": False}
    deviation = {"deviation_bonus": 0.15}

    result = apply_baseline_adjustment(
        global_risk_score=0.30,
        deviation=deviation,
        quality_info=quality_info,
        baseline_ready=False,
    )
    assert result["final_risk_score"] == pytest.approx(0.30, abs=0.001)
    assert result["baseline_ready"] is False


def test_apply_adjustment_baseline_ready_adds_bonus():
    """When baseline is ready and HR deviates, final_risk > global_risk."""
    from services.baseline_service import apply_baseline_adjustment

    quality_info = {"quality_confidence": 0.9, "quality_warning": None, "safety_override": False}
    deviation = {"deviation_bonus": 0.10}

    result = apply_baseline_adjustment(
        global_risk_score=0.30,
        deviation=deviation,
        quality_info=quality_info,
        baseline_ready=True,
    )
    assert result["final_risk_score"] == pytest.approx(0.40, abs=0.001)
    assert result["personal_deviation_score"] == pytest.approx(0.10, abs=0.001)


def test_apply_adjustment_low_quality_no_bonus():
    """Low quality_confidence should suppress personal_deviation_score."""
    from services.baseline_service import apply_baseline_adjustment

    quality_info = {"quality_confidence": 0.3, "quality_warning": "Low quality", "safety_override": False}
    deviation = {"deviation_bonus": 0.15}

    result = apply_baseline_adjustment(
        global_risk_score=0.30,
        deviation=deviation,
        quality_info=quality_info,
        baseline_ready=True,
    )
    # quality < 0.5 and no safety_override → personal deviation suppressed
    assert result["personal_deviation_score"] == pytest.approx(0.0, abs=0.001)
    assert result["final_risk_score"] == pytest.approx(0.30, abs=0.001)


def test_apply_adjustment_safety_override_passes_bonus():
    """Safety override allows deviation bonus even with low quality."""
    from services.baseline_service import apply_baseline_adjustment

    quality_info = {"quality_confidence": 0.2, "quality_warning": "Low quality", "safety_override": True}
    deviation = {"deviation_bonus": 0.10}

    result = apply_baseline_adjustment(
        global_risk_score=0.30,
        deviation=deviation,
        quality_info=quality_info,
        baseline_ready=True,
    )
    assert result["final_risk_score"] == pytest.approx(0.40, abs=0.001)


def test_apply_adjustment_high_sensitivity_stored():
    """alert_sensitivity is stored in the breakdown dict."""
    from services.baseline_service import apply_baseline_adjustment

    quality_info = {"quality_confidence": 0.9, "quality_warning": None, "safety_override": False}
    deviation = {"deviation_bonus": 0.05}

    result = apply_baseline_adjustment(
        global_risk_score=0.50,
        deviation=deviation,
        quality_info=quality_info,
        baseline_ready=True,
        alert_sensitivity="high",
    )
    assert result["alert_sensitivity"] == "high"
    # Risk score is NOT affected by sensitivity (only thresholds change)
    assert result["final_risk_score"] == pytest.approx(0.55, abs=0.001)


# ===========================================================================
# 7. DevicePacketResponse backward compatibility
# ===========================================================================

def test_packet_response_risk_breakdown_optional():
    """DevicePacketResponse must work without risk_breakdown (backward compat)."""
    from schemas import DevicePacketResponse

    resp = DevicePacketResponse(status="accepted", packet_seq=1, device_id="dev1")
    assert resp.user_id is None
    assert resp.risk_breakdown is None


def test_packet_response_with_risk_breakdown():
    """DevicePacketResponse should accept risk_breakdown dict."""
    from schemas import DevicePacketResponse

    breakdown = {
        "final_risk_score": 0.35,
        "global_risk_score": 0.30,
        "personal_deviation_score": 0.05,
        "baseline_ready": True,
        "quality_confidence": 0.90,
        "quality_warning": None,
    }
    resp = DevicePacketResponse(
        status="accepted", packet_seq=1, device_id="dev1",
        user_id="u1", risk_breakdown=breakdown,
    )
    assert resp.risk_breakdown["final_risk_score"] == 0.35


# ===========================================================================
# 8. Factory / Hybrid mode import safety
# ===========================================================================

def test_factory_sqlite_has_baselines_field():
    """RepoSet from sqlite mode must have a baselines attribute."""
    from unittest.mock import MagicMock
    from repositories.factory import get_repos
    from repositories.sqlite.repos import SqliteBaselineRepo

    mock_db = MagicMock()
    repos = get_repos(db=mock_db, mode="sqlite")
    assert hasattr(repos, "baselines")
    assert isinstance(repos.baselines, SqliteBaselineRepo)


def test_factory_firebase_has_baselines_field():
    """RepoSet from firebase mode must have a baselines attribute."""
    pytest.importorskip("google.cloud.firestore_v1", reason="google-cloud-firestore not installed")

    from repositories.factory import get_repos
    from repositories.firebase.repos import FirebaseBaselineRepo

    repos = get_repos(db=None, mode="firebase")
    assert hasattr(repos, "baselines")
    assert isinstance(repos.baselines, FirebaseBaselineRepo)


def test_factory_hybrid_baselines_is_sqlite():
    """In hybrid mode, baselines must be the SQLite repo (not a HybridRepo wrapper)."""
    from unittest.mock import MagicMock, patch
    from repositories.factory import get_repos, _build_firebase
    from repositories.sqlite.repos import SqliteBaselineRepo

    mock_db = MagicMock()
    # Patch _build_firebase to avoid real Firestore client
    with patch("repositories.factory._build_firebase") as mock_fb:
        mock_fb_repos = MagicMock()
        mock_fb.return_value = mock_fb_repos
        repos = get_repos(db=mock_db, mode="hybrid")

    assert hasattr(repos, "baselines")
    assert isinstance(repos.baselines, SqliteBaselineRepo)


# ===========================================================================
# 9. AppSettings alert_sensitivity schema
# ===========================================================================

def test_settings_response_has_alert_sensitivity():
    from schemas import SettingsResponse

    resp = SettingsResponse(
        user_id="u1",
        notifications_enabled=True,
        battery_mode="balanced",
        background_monitoring=True,
        update_interval_seconds=4,
    )
    # alert_sensitivity has a default of "normal"
    assert resp.alert_sensitivity == "normal"


def test_settings_update_alert_sensitivity_field():
    from schemas import SettingsUpdate

    upd = SettingsUpdate(alert_sensitivity="high")
    assert upd.alert_sensitivity == "high"
