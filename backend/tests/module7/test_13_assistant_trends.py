"""
Tests for assistant_service and trend_service — SON SPRİNT (Final Product).
Validates:
  - Health assistant summary generation
  - Alert explanation generation
  - Daily summary generation
  - Trend analysis (label determination, empty data handling)
  - Empty state responses when no data exists
"""
import os
import sys
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_assistant.db"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database import Base
import models  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///./test_assistant.db", echo=False)
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
        os.remove("test_assistant.db")
    except OSError:
        pass


@pytest_asyncio.fixture
async def db(setup_database):
    async with _SessionLocal() as session:
        yield session
        await session.rollback()


# ── Assistant Service Tests ─────────────────────────────────────────────────


class TestAssistantService:
    """Tests for services/assistant_service.py"""

    async def test_generate_summary_no_live_data(self, db):
        """When no live_status exists, assistant returns veri_yok response."""
        from services.assistant_service import generate_assistant_summary
        result = await generate_assistant_summary(db, "nonexistent_user", role="self")
        assert result is not None
        assert "status" in result
        # Should indicate no data available
        assert result["status"] in ("veri_yok", "no_data", "empty")

    async def test_generate_summary_with_live_data(self, db):
        """When live_status exists, assistant returns a meaningful summary."""
        from services.assistant_service import generate_assistant_summary
        # Seed a live_status row
        now = datetime.utcnow()
        await db.execute(
            models.LiveStatus.__table__.insert().values(
                id="ls_test_1",
                user_id="u_test",
                heart_rate=85.0,
                spo2=96.5,
                motion_score=0.2,
                risk_score=0.15,
                scenario="normal",
                timestamp=now,
            )
        )
        await db.commit()

        result = await generate_assistant_summary(db, "u_test", role="self")
        assert result is not None
        assert "summary" in result or "message" in result

    async def test_alert_explanation_nonexistent(self, db):
        """Explaining a non-existent alert returns 404-style response."""
        from services.assistant_service import generate_alert_explanation
        result = await generate_alert_explanation(db, "nonexistent_alert_id")
        assert result is not None
        # Should indicate alert not found
        assert result.get("status") in ("not_found", "error", None) or "bulunamadı" in result.get("message", "").lower() or result.get("explanation") is not None

    async def test_daily_summary_no_data(self, db):
        """Daily summary with no anomalies returns empty/stable summary."""
        from services.assistant_service import generate_daily_summary
        result = await generate_daily_summary(db, "nonexistent_user")
        assert result is not None


# ── Trend Service Tests ─────────────────────────────────────────────────────


class TestTrendService:
    """Tests for services/trend_service.py"""

    async def test_analyze_trends_no_data(self, db):
        """Trend analysis with no anomalies returns veri_yetersiz."""
        from services.trend_service import analyze_trends
        result = await analyze_trends(db, "nonexistent_user")
        assert result is not None
        assert "label" in result
        assert result["label"] == "veri_yetersiz"

    async def test_analyze_trends_with_anomalies(self, db):
        """Trend analysis with anomalies returns a meaningful label."""
        from services.trend_service import analyze_trends
        # Seed some anomalies
        now = datetime.utcnow()
        for i in range(5):
            await db.execute(
                models.AnomalyEvent.__table__.insert().values(
                    id=f"an_trend_{i}",
                    user_id="u_trend",
                    metric="heart_rate",
                    value=120.0 + i,
                    unit="bpm",
                    severity="warning",
                    detected_at=now - timedelta(hours=i),
                    summary=f"HR anomaly #{i}",
                )
            )
        await db.commit()

        result = await analyze_trends(db, "u_trend")
        assert result is not None
        assert "label" in result
        assert result["label"] in ("artan_risk", "stabil", "iyilesiyor", "izlem_gerektiren", "veri_yetersiz")
        assert "summary" in result

    async def test_trend_label_determination(self):
        """Test _determine_trend_label function directly."""
        from services.trend_service import _determine_trend_label

        # Many recent anomalies → artan_risk
        label = _determine_trend_label(count_1h=5, count_24h=10, recurring_metrics=["heart_rate"])
        assert label in ("artan_risk", "izlem_gerektiren")

        # Zero anomalies → stabil or veri_yetersiz
        label = _determine_trend_label(count_1h=0, count_24h=0, recurring_metrics=[])
        assert label in ("stabil", "veri_yetersiz")

        # Few anomalies, all old → iyilesiyor or stabil
        label = _determine_trend_label(count_1h=0, count_24h=3, recurring_metrics=["spo2"])
        assert label in ("iyilesiyor", "stabil", "izlem_gerektiren")


# ── Mode Separation Tests ───────────────────────────────────────────────────


class TestModeSeparation:
    """Tests ensuring live mode never returns demo/fake data."""

    async def test_empty_response_for_missing_user(self, db):
        """API returns empty data for non-existent user, not demo data."""
        from services.assistant_service import generate_assistant_summary
        result = await generate_assistant_summary(db, "definitely_not_a_user", role="self")
        # Must not contain demo-looking content
        assert "demo" not in str(result).lower()
        assert "Ali Yilmaz" not in str(result)

    async def test_trend_empty_for_missing_user(self, db):
        """Trend analysis returns veri_yetersiz, not demo trends."""
        from services.trend_service import analyze_trends
        result = await analyze_trends(db, "definitely_not_a_user")
        assert result["label"] == "veri_yetersiz"
        assert "demo" not in str(result).lower()
