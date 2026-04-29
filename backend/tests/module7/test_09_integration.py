"""
Integration tests — ingestion chain, AI bridge, link-code hardening.
Uses a real async SQLite database and the repository layer.
"""
import os
import sys
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_integration.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///./test_integration.db", echo=False)
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
        os.remove("test_integration.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def repos(db):
    from repositories.factory import get_repos
    return get_repos(db=db)


_user_counter = 0


def _next_id():
    global _user_counter
    _user_counter += 1
    return str(_user_counter)


@pytest_asyncio.fixture
async def seed_self_user(db, repos):
    """Create a SELF user and return their id."""
    uid = f"self-{_next_id()}"
    user = await repos.users.create({
        "id": uid, "email": f"{uid}@test.com",
        "password_hash": "h", "role": "SELF", "full_name": "Self User",
    })
    await db.commit()
    return user["id"]


@pytest_asyncio.fixture
async def seed_relative_user(db, repos):
    """Create a RELATIVE user and return their id."""
    uid = f"rel-{_next_id()}"
    user = await repos.users.create({
        "id": uid, "email": f"{uid}@test.com",
        "password_hash": "h", "role": "RELATIVE", "full_name": "Relative User",
    })
    await db.commit()
    return user["id"]


# ===================================================================
# Ingestion chain helper tests
# ===================================================================

class TestIngestionHelpers:
    def test_risk_to_severity_critical(self):
        from routers.ingestion_router import _risk_to_severity
        assert _risk_to_severity(0.80) == "critical"

    def test_risk_to_severity_warning(self):
        from routers.ingestion_router import _risk_to_severity
        assert _risk_to_severity(0.60) == "warning"

    def test_risk_to_severity_watch(self):
        from routers.ingestion_router import _risk_to_severity
        assert _risk_to_severity(0.35) == "watch"

    def test_risk_to_severity_none(self):
        from routers.ingestion_router import _risk_to_severity
        assert _risk_to_severity(0.10) is None

    def test_get_recommendations_critical(self):
        from routers.ingestion_router import _get_recommendations
        recs = _get_recommendations("critical")
        assert len(recs) >= 2
        assert any("emergency" in r.lower() or "Emergency" in r for r in recs)

    def test_get_recommendations_warning(self):
        from routers.ingestion_router import _get_recommendations
        recs = _get_recommendations("warning")
        assert len(recs) >= 2

    def test_determine_anomaly_metric_low_spo2(self):
        from routers.ingestion_router import _determine_anomaly_metric
        metric, value, unit, _ = _determine_anomaly_metric(80, 88, True, True, 0.1)
        assert metric == "SpO2"
        assert value == 88

    def test_determine_anomaly_metric_high_hr(self):
        from routers.ingestion_router import _determine_anomaly_metric
        metric, value, unit, _ = _determine_anomaly_metric(130, 97, True, True, 0.1)
        assert metric == "Heart Rate"
        assert value == 130

    def test_determine_anomaly_metric_motion(self):
        from routers.ingestion_router import _determine_anomaly_metric
        metric, value, unit, _ = _determine_anomaly_metric(72, 97, True, True, 0.8)
        assert metric == "Motion"


# ===================================================================
# AI bridge service tests
# ===================================================================

class TestAIBridge:
    @pytest.mark.asyncio
    async def test_normal_risk_creates_nothing(self, db, repos, seed_self_user):
        from services.ai_bridge import process_ai_result
        ai_output = {
            "fall_probability": 0.05,
            "instability_probability": 0.02,
            "early_risk_score": 0.1,
            "final_risk_level": "normal",
            "immediate_alert": False,
            "confidence": 0.95,
            "reasons": [],
            "recommendations": ["All parameters normal"],
        }
        result = await process_ai_result(repos, seed_self_user, ai_output)
        assert result["risk_level"] == "normal"
        assert result["anomaly_id"] is None
        assert result["alert_id"] is None
        assert result["notifications_sent"] == 0

    @pytest.mark.asyncio
    async def test_watch_creates_anomaly_no_alert(self, db, repos, seed_self_user):
        from services.ai_bridge import process_ai_result
        ai_output = {
            "fall_probability": 0.15,
            "instability_probability": 0.3,
            "early_risk_score": 0.4,
            "final_risk_level": "watch",
            "immediate_alert": False,
            "confidence": 0.8,
            "reasons": ["Mild instability"],
            "recommendations": ["Rest recommended"],
        }
        result = await process_ai_result(repos, seed_self_user, ai_output)
        assert result["risk_level"] == "watch"
        assert result["anomaly_id"] is not None
        assert result["alert_id"] is None  # watch does not create alerts

    @pytest.mark.asyncio
    async def test_critical_creates_anomaly_and_alert(self, db, repos, seed_self_user):
        from services.ai_bridge import process_ai_result
        ai_output = {
            "fall_probability": 0.85,
            "instability_probability": 0.7,
            "early_risk_score": 0.9,
            "final_risk_level": "critical",
            "immediate_alert": True,
            "confidence": 0.95,
            "reasons": ["Fall risk very high"],
            "recommendations": ["Do not move"],
        }
        result = await process_ai_result(repos, seed_self_user, ai_output)
        assert result["risk_level"] == "critical"
        assert result["anomaly_id"] is not None
        assert result["alert_id"] is not None

    @pytest.mark.asyncio
    async def test_critical_with_linked_user_sends_notifications(self, db, repos, seed_self_user, seed_relative_user):
        from services.ai_bridge import process_ai_result

        # Link the relative to the self user
        await repos.relations.create({
            "id": "rel-link-1",
            "self_user_id": seed_self_user,
            "linked_user_id": seed_relative_user,
            "relation_type": "RELATIVE",
            "is_active": True,
        })
        await db.commit()

        ai_output = {
            "fall_probability": 0.92,
            "instability_probability": 0.8,
            "early_risk_score": 0.95,
            "final_risk_level": "critical",
            "immediate_alert": True,
            "confidence": 0.98,
            "reasons": ["Severe fall risk"],
            "recommendations": ["Emergency assistance needed"],
        }
        result = await process_ai_result(repos, seed_self_user, ai_output)
        assert result["notifications_sent"] >= 1

    @pytest.mark.asyncio
    async def test_ai_bridge_updates_live_status(self, db, repos, seed_self_user):
        from services.ai_bridge import process_ai_result
        ai_output = {
            "fall_probability": 0.1,
            "instability_probability": 0.05,
            "early_risk_score": 0.15,
            "final_risk_level": "normal",
            "immediate_alert": False,
            "confidence": 0.9,
            "reasons": [],
            "recommendations": [],
        }
        vitals = {"heart_rate": 85.0, "spo2": 96.0}
        await process_ai_result(repos, seed_self_user, ai_output, vitals)
        status = await repos.live_status.get_by_user(seed_self_user)
        assert status is not None
        assert status["heart_rate"] == 85.0
        assert status["spo2"] == 96.0


# ===================================================================
# AI inference schema validation
# ===================================================================

class TestAIInferenceSchema:
    def test_valid_request(self):
        from schemas import AIInferenceRequest
        req = AIInferenceRequest(
            user_id="u1",
            fall_probability=0.5,
            final_risk_level="warning",
        )
        assert req.user_id == "u1"
        assert req.final_risk_level == "warning"

    def test_invalid_risk_level_rejected(self):
        from schemas import AIInferenceRequest
        with pytest.raises(Exception):
            AIInferenceRequest(user_id="u1", final_risk_level="extreme")

    def test_defaults_are_safe(self):
        from schemas import AIInferenceRequest
        req = AIInferenceRequest(user_id="u1")
        assert req.final_risk_level == "normal"
        assert req.fall_probability == 0.0
        assert req.immediate_alert is False


# ===================================================================
# Link code hardening
# ===================================================================

class TestLinkCodeHardening:
    @pytest.mark.asyncio
    async def test_code_expiry_check(self, db, repos):
        from datetime import datetime, timedelta
        owner_id = f"lc-owner-{_next_id()}"
        await repos.users.create({
            "id": owner_id, "email": f"{owner_id}@test.com",
            "password_hash": "h", "role": "DOCTOR", "full_name": "Doc",
        })
        code_id = f"lc-{_next_id()}"
        code_val = f"99{_user_counter:04d}"
        # Create expired code
        await repos.link_codes.create({
            "id": code_id,
            "code": code_val,
            "owner_id": owner_id,
            "code_type": "DOCTOR",
            "is_active": True,
            "uses_remaining": 5,
            "expires_at": datetime.utcnow() - timedelta(hours=1),
        })
        await db.commit()
        code = await repos.link_codes.get_by_code(code_val)
        assert code is not None
        assert code["expires_at"] < datetime.utcnow()

    @pytest.mark.asyncio
    async def test_duplicate_relation_prevention(self, db, repos):
        # Create users
        s_id = f"dup-self-{_next_id()}"
        r_id = f"dup-rel-{_next_id()}"
        await repos.users.create({
            "id": s_id, "email": f"{s_id}@test.com",
            "password_hash": "h", "role": "SELF", "full_name": "S1",
        })
        await repos.users.create({
            "id": r_id, "email": f"{r_id}@test.com",
            "password_hash": "h", "role": "RELATIVE", "full_name": "R1",
        })
        await repos.relations.create({
            "id": f"dup-link-{_next_id()}",
            "self_user_id": s_id,
            "linked_user_id": r_id,
            "relation_type": "RELATIVE",
            "is_active": True,
        })
        await db.commit()

        # Forward direction check
        existing = await repos.relations.find_active_link(s_id, r_id)
        assert existing is not None

    @pytest.mark.asyncio
    async def test_code_uses_decrement(self, db, repos):
        from datetime import datetime, timedelta
        owner_id = f"lc-owner2-{_next_id()}"
        await repos.users.create({
            "id": owner_id, "email": f"{owner_id}@test.com",
            "password_hash": "h", "role": "DOCTOR", "full_name": "Doc2",
        })
        code_id = f"lc-dec-{_next_id()}"
        code_val = f"88{_user_counter:04d}"
        await repos.link_codes.create({
            "id": code_id,
            "code": code_val,
            "owner_id": owner_id,
            "code_type": "DOCTOR",
            "is_active": True,
            "uses_remaining": 3,
            "expires_at": datetime.utcnow() + timedelta(hours=24),
        })
        await db.commit()
        code = await repos.link_codes.get_by_code(code_val)
        assert code["uses_remaining"] == 3

        # Simulate decrement
        await repos.link_codes.update(code["id"], {"uses_remaining": 2})
        await db.commit()
        updated = await repos.link_codes.get_by_code(code_val)
        assert updated["uses_remaining"] == 2

    @pytest.mark.asyncio
    async def test_code_deactivation_on_zero_uses(self, db, repos):
        from datetime import datetime, timedelta
        owner_id = f"lc-owner3-{_next_id()}"
        await repos.users.create({
            "id": owner_id, "email": f"{owner_id}@test.com",
            "password_hash": "h", "role": "DOCTOR", "full_name": "Doc3",
        })
        code_id = f"lc-deact-{_next_id()}"
        code_val = f"77{_user_counter:04d}"
        await repos.link_codes.create({
            "id": code_id,
            "code": code_val,
            "owner_id": owner_id,
            "code_type": "DOCTOR",
            "is_active": True,
            "uses_remaining": 1,
            "expires_at": datetime.utcnow() + timedelta(hours=24),
        })
        await db.commit()

        # Simulate full use
        await repos.link_codes.update(code_id, {"uses_remaining": 0, "is_active": False})
        await db.commit()
        code = await repos.link_codes.get_by_code(code_val)
        assert code["uses_remaining"] == 0
        assert code["is_active"] is False


# ===================================================================
# Risk score computation — edge cases
# ===================================================================

class TestRiskScoreEdgeCases:
    def test_all_invalid_vitals(self):
        from routers.ingestion_router import _compute_risk_score
        score = _compute_risk_score(0, 0, False, False, 0.0)
        assert score == 0.0

    def test_max_combined_clamp(self):
        from routers.ingestion_router import _compute_risk_score
        # extreme HR + extreme SpO2 + max motion
        score = _compute_risk_score(200, 60, True, True, 1.0)
        assert score <= 1.0

    def test_motion_only(self):
        from routers.ingestion_router import _compute_risk_score
        score = _compute_risk_score(72, 98, False, False, 0.5)
        assert 0.05 <= score <= 0.15  # motion * 0.2

    def test_low_hr_adds_risk(self):
        from routers.ingestion_router import _compute_risk_score
        score = _compute_risk_score(40, 98, True, True, 0.0)
        assert score >= 0.2


# ===================================================================
# AI bridge metric selection
# ===================================================================

class TestAIBridgeMetricSelection:
    def test_high_fall_prob_dominates(self):
        from services.ai_bridge import _pick_dominant_metric
        metric, _, _, _ = _pick_dominant_metric(
            {"fall_probability": 0.8, "instability_probability": 0.3, "early_risk_score": 0.7},
            {"heart_rate": 80, "spo2": 97},
        )
        assert metric == "Fall Risk"

    def test_low_spo2_dominates_over_instability(self):
        from services.ai_bridge import _pick_dominant_metric
        metric, _, _, _ = _pick_dominant_metric(
            {"fall_probability": 0.1, "instability_probability": 0.6, "early_risk_score": 0.5},
            {"heart_rate": 80, "spo2": 88},
        )
        assert metric == "SpO2"

    def test_high_hr_detected(self):
        from services.ai_bridge import _pick_dominant_metric
        metric, _, _, _ = _pick_dominant_metric(
            {"fall_probability": 0.1, "instability_probability": 0.3, "early_risk_score": 0.4},
            {"heart_rate": 140, "spo2": 97},
        )
        assert metric == "Heart Rate"

    def test_fallback_combined(self):
        from services.ai_bridge import _pick_dominant_metric
        metric, _, _, _ = _pick_dominant_metric(
            {"fall_probability": 0.1, "instability_probability": 0.2, "early_risk_score": 0.3},
            {"heart_rate": 80, "spo2": 97},
        )
        assert metric == "Combined Risk"
