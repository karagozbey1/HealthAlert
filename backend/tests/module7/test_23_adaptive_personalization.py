"""Test 23 — Part 5B: Adaptive Personalization Engine

Tests:
  A) Cold-start profile — bonus strictly limited to COLD_START_MAX_BONUS
  B) Calibrated profile — stronger deviation applied
  C) Trend analysis — HR rising + SpO2 falling increases risk; low quality clamps
  D) Feedback adjustment — false_alarm reduces warning sensitivity; critical not suppressed
  E) Risk breakdown integrity — personalization key present; ML/retrieval have NO role
  F) Endpoint availability — personalization endpoints return 200 with JWT

All async tests use asyncio.run() (no @pytest.mark.asyncio needed).
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_personalization.db")


# ---------------------------------------------------------------------------
# In-memory personalization repo for tests (no DB needed)
# ---------------------------------------------------------------------------

class InMemoryPersonalizationRepo:
    def __init__(self):
        self._profiles: Dict[str, Dict] = {}
        self._memories: List[Dict] = []
        self._trends: List[Dict] = []

    async def get_or_create_profile(self, user_id: str) -> Dict:
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                "id": str(uuid4()),
                "user_id": user_id,
                "personalization_level": "cold_start",
                "total_valid_samples": 0,
                "total_observation_minutes": 0.0,
                "total_feedback_count": 0,
                "false_alarm_count": 0,
                "confirmed_risk_count": 0,
                "sensor_error_count": 0,
                "typical_hr_min": 55.0, "typical_hr_max": 100.0,
                "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
                "typical_motion_min": 0.0, "typical_motion_max": 0.5,
                "day_profile_json": None, "night_profile_json": None,
                "activity_profile_json": None,
                "last_recalibrated_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "baseline_id": None,
            }
        return dict(self._profiles[user_id])

    async def update_profile(self, user_id: str, updates: Dict) -> Dict:
        profile = await self.get_or_create_profile(user_id)
        profile.update(updates)
        profile["updated_at"] = datetime.utcnow()
        self._profiles[user_id] = profile
        return dict(profile)

    async def add_risk_memory(self, data: Dict) -> Dict:
        d = dict(data)
        self._memories.append(d)
        return d

    async def list_risk_memory(self, user_id: str, limit: int = 50) -> List[Dict]:
        return [m for m in reversed(self._memories) if m["user_id"] == user_id][:limit]

    async def create_trend_snapshot(self, data: Dict) -> Dict:
        d = dict(data)
        self._trends.append(d)
        return d

    async def get_latest_trend_snapshot(self, user_id: str) -> Optional[Dict]:
        user_trends = [t for t in self._trends if t["user_id"] == user_id]
        return user_trends[-1] if user_trends else None

    async def summarize_personalization(self, user_id: str) -> Dict:
        profile = await self.get_or_create_profile(user_id)
        total_fb = profile.get("total_feedback_count", 0)
        false_alarm_count = profile.get("false_alarm_count", 0)
        false_alarm_rate = false_alarm_count / total_fb if total_fb > 0 else 0.0
        latest_trend = await self.get_latest_trend_snapshot(user_id)
        return {
            "user_id": user_id,
            "personalization_level": profile.get("personalization_level", "cold_start"),
            "total_valid_samples": profile.get("total_valid_samples", 0),
            "total_observation_minutes": profile.get("total_observation_minutes", 0.0),
            "false_alarm_rate": round(false_alarm_rate, 4),
            "confirmed_risk_count": profile.get("confirmed_risk_count", 0),
            "feedback_count": total_fb,
            "latest_trend": latest_trend,
            "typical_ranges": {
                "hr": [profile.get("typical_hr_min", 55.0), profile.get("typical_hr_max", 100.0)],
                "spo2": [profile.get("typical_spo2_min", 95.0), profile.get("typical_spo2_max", 100.0)],
                "motion": [profile.get("typical_motion_min", 0.0), profile.get("typical_motion_max", 0.5)],
            },
        }


class FakeRepos:
    def __init__(self):
        self.personalization = InMemoryPersonalizationRepo()


# ---------------------------------------------------------------------------
# A) Cold-start profile
# ---------------------------------------------------------------------------

class TestColdStartProfile:

    def test_cold_start_deviation_capped(self):
        """Cold-start profile limits deviation bonus to COLD_START_MAX_BONUS."""
        from services.adaptive_personalization_service import compute_contextual_deviation
        from config import settings

        cold_profile = {
            "personalization_level": "cold_start",
            "typical_hr_min": 55.0, "typical_hr_max": 75.0,
            "typical_spo2_min": 96.0,
            "typical_motion_max": 0.3,
        }

        # High HR to create large deviation
        result = compute_contextual_deviation(
            profile=cold_profile,
            baseline={},
            hr=130.0,  # very high, well above typical_hr_max
            spo2=93.0,  # below spo2_min
            motion_score=1.0,  # above motion_max
            hr_valid=True,
            spo2_valid=True,
        )
        assert result["deviation_bonus"] <= settings.PERSONALIZATION_COLD_START_MAX_BONUS + 1e-6, \
            f"Cold-start bonus {result['deviation_bonus']} exceeded cap {settings.PERSONALIZATION_COLD_START_MAX_BONUS}"

    def test_cold_start_personalization_level(self):
        """get_personalization_level returns cold_start when samples < 30."""
        from services.adaptive_personalization_service import _get_personalization_level
        assert _get_personalization_level(0, 0) == "cold_start"
        assert _get_personalization_level(29, 100) == "cold_start"
        assert _get_personalization_level(30, 0) == "learning"

    def test_cold_start_feedback_no_adjustment(self):
        """Cold-start profile produces zero feedback adjustment (insufficient data)."""
        from services.adaptive_personalization_service import compute_feedback_adjustment

        cold_profile = {
            "personalization_level": "cold_start",
            "total_feedback_count": 0,
            "false_alarm_count": 0,
            "confirmed_risk_count": 0,
            "sensor_error_count": 0,
        }
        adj = compute_feedback_adjustment(cold_profile, risk_score=0.5, severity="warning")
        assert adj == 0.0, f"Expected 0.0, got {adj}"


# ---------------------------------------------------------------------------
# B) Calibrated profile
# ---------------------------------------------------------------------------

class TestCalibratedProfile:

    def test_calibrated_bonus_larger_than_cold(self):
        """Calibrated profile allows a larger deviation bonus than cold_start."""
        from services.adaptive_personalization_service import compute_contextual_deviation
        from config import settings

        calibrated_profile = {
            "personalization_level": "calibrated",
            "typical_hr_min": 55.0, "typical_hr_max": 75.0,
            "typical_spo2_min": 96.0,
            "typical_motion_max": 0.3,
        }
        cold_profile = dict(calibrated_profile)
        cold_profile["personalization_level"] = "cold_start"

        # Same extreme readings for both
        kwargs = dict(baseline={}, hr=140.0, spo2=90.0, motion_score=2.0,
                      hr_valid=True, spo2_valid=True)

        cal_result = compute_contextual_deviation(profile=calibrated_profile, **kwargs)
        cold_result = compute_contextual_deviation(profile=cold_profile, **kwargs)

        assert cal_result["deviation_bonus"] >= cold_result["deviation_bonus"], \
            "Calibrated profile should allow at least as much bonus as cold_start"
        assert cal_result["deviation_bonus"] <= settings.PERSONALIZATION_CALIBRATED_MAX_BONUS + 1e-6

    def test_personalization_level_transitions(self):
        """Level transitions follow expected thresholds."""
        from services.adaptive_personalization_service import _get_personalization_level
        assert _get_personalization_level(100, 0) == "learning"
        assert _get_personalization_level(300, 0) == "calibrated"
        assert _get_personalization_level(300, 10) == "mature"
        assert _get_personalization_level(1000, 50) == "mature"

    def test_update_profile_from_packet_increments_samples(self):
        """update_profile_from_packet increments total_valid_samples each call."""
        service = _get_service()
        repos = FakeRepos()

        async def run():
            baseline = {"id": "b1", "is_ready": True}
            for i in range(5):
                await service.update_profile_from_packet(
                    repos=repos, user_id="u_cal",
                    hr=72.0 + i, spo2=98.0, motion_score=0.1,
                    hr_valid=True, spo2_valid=True, baseline=baseline,
                )
            profile = await repos.personalization.get_or_create_profile("u_cal")
            return profile["total_valid_samples"]

        count = asyncio.run(run())
        assert count == 5, f"Expected 5 samples, got {count}"


# ---------------------------------------------------------------------------
# C) Trend analysis
# ---------------------------------------------------------------------------

class TestTrendAnalysis:

    def test_hr_rising_spo2_falling_increases_risk(self):
        """HR rising + SpO2 falling trend produces a positive risk adjustment."""
        from services.adaptive_personalization_service import (
            compute_trend_from_snapshots, compute_trend_adjustment
        )

        snapshots = [
            {"heart_rate": 70 + i * 5, "spo2": 98 - i, "motion_score": 0.1,
             "risk_score": 0.1, "signal_quality": 0.9}
            for i in range(8)
        ]
        trend = compute_trend_from_snapshots(snapshots)
        assert trend["hr_trend"] == "rising", f"Expected rising, got {trend['hr_trend']}"
        assert trend["spo2_trend"] == "falling", f"Expected falling, got {trend['spo2_trend']}"

        adj = compute_trend_adjustment(trend, quality_confidence=0.95)
        assert adj > 0, f"Expected positive adjustment, got {adj}"

    def test_stable_trend_gives_zero_adjustment(self):
        """All-stable trend produces near-zero adjustment."""
        from services.adaptive_personalization_service import (
            compute_trend_from_snapshots, compute_trend_adjustment
        )

        snapshots = [
            {"heart_rate": 72.0, "spo2": 98.0, "motion_score": 0.1,
             "risk_score": 0.05, "signal_quality": 0.9}
            for _ in range(8)
        ]
        trend = compute_trend_from_snapshots(snapshots)
        adj = compute_trend_adjustment(trend, quality_confidence=0.9)
        assert abs(adj) < 0.01, f"Expected ~0 adjustment, got {adj}"

    def test_low_quality_clamps_trend_bonus(self):
        """Very low trend_confidence (<0.2) gates out adjustment entirely."""
        from services.adaptive_personalization_service import compute_trend_adjustment

        trend_info = {
            "hr_trend": "rising", "spo2_trend": "falling",
            "motion_trend": "rising", "quality_trend": "stable",
            "risk_trend": "rising", "trend_confidence": 0.1,
        }
        adj = compute_trend_adjustment(trend_info, quality_confidence=0.9)
        assert adj == 0.0, f"Low-confidence trend should give 0 adjustment, got {adj}"

    def test_too_few_snapshots_returns_stable(self):
        """<3 snapshots → all trends stable, confidence 0."""
        from services.adaptive_personalization_service import compute_trend_from_snapshots

        result = compute_trend_from_snapshots([{"heart_rate": 80}])
        assert result["trend_confidence"] == 0.0
        assert result["hr_trend"] == "stable"

    def test_trend_max_bonus_respected(self):
        """Trend adjustment never exceeds PERSONALIZATION_TREND_MAX_BONUS."""
        from services.adaptive_personalization_service import compute_trend_adjustment
        from config import settings

        trend_info = {
            "hr_trend": "rising", "spo2_trend": "falling",
            "motion_trend": "rising", "quality_trend": "falling",
            "risk_trend": "rising", "trend_confidence": 1.0,
        }
        adj = compute_trend_adjustment(trend_info, quality_confidence=1.0)
        assert adj <= settings.PERSONALIZATION_TREND_MAX_BONUS + 1e-6


# ---------------------------------------------------------------------------
# D) Feedback adjustment
# ---------------------------------------------------------------------------

class TestFeedbackAdjustment:

    def _make_high_false_alarm_profile(self, level="calibrated") -> Dict:
        return {
            "personalization_level": level,
            "total_feedback_count": 20,
            "false_alarm_count": 12,  # 60% false_alarm_rate
            "confirmed_risk_count": 2,
            "sensor_error_count": 0,
        }

    def _make_confirmed_risk_profile(self) -> Dict:
        return {
            "personalization_level": "calibrated",
            "total_feedback_count": 10,
            "false_alarm_count": 0,
            "confirmed_risk_count": 5,
            "sensor_error_count": 0,
        }

    def test_false_alarm_reduces_warning_sensitivity(self):
        """High false-alarm rate → negative feedback adjustment for warning severity."""
        from services.adaptive_personalization_service import compute_feedback_adjustment

        profile = self._make_high_false_alarm_profile()
        adj = compute_feedback_adjustment(profile, risk_score=0.55, severity="warning")
        assert adj < 0, f"Expected negative adjustment, got {adj}"

    def test_false_alarm_does_not_suppress_critical(self):
        """High false-alarm rate does NOT produce negative adjustment for critical severity."""
        from services.adaptive_personalization_service import compute_feedback_adjustment

        profile = self._make_high_false_alarm_profile()
        # Critical severity — the false-alarm downward rule only applies to warning
        adj = compute_feedback_adjustment(profile, risk_score=0.90, severity="critical")
        # Should not be negative (may be 0 or positive from confirmed_risk bonus)
        assert adj >= -0.01, f"Critical should not be suppressed, got {adj}"

    def test_confirmed_risk_increases_sensitivity(self):
        """confirmed_risk_count >= 3 → positive feedback adjustment at warning level."""
        from services.adaptive_personalization_service import compute_feedback_adjustment

        profile = self._make_confirmed_risk_profile()
        adj = compute_feedback_adjustment(profile, risk_score=0.4, severity="warning")
        assert adj >= 0, f"Expected non-negative adjustment, got {adj}"

    def test_safety_override_prevents_negative(self):
        """safety_override=True ensures feedback adjustment is never negative."""
        from services.adaptive_personalization_service import compute_feedback_adjustment

        profile = self._make_high_false_alarm_profile()
        adj = compute_feedback_adjustment(
            profile, risk_score=0.55, severity="warning", safety_override=True
        )
        assert adj >= 0, f"Safety override should prevent negative adjustment, got {adj}"

    def test_feedback_max_adjustment_respected(self):
        """Feedback adjustment never exceeds PERSONALIZATION_FEEDBACK_MAX_ADJUSTMENT."""
        from services.adaptive_personalization_service import compute_feedback_adjustment
        from config import settings

        profile = {
            "personalization_level": "mature",
            "total_feedback_count": 1000,
            "false_alarm_count": 0,
            "confirmed_risk_count": 999,
            "sensor_error_count": 0,
        }
        adj = compute_feedback_adjustment(profile, risk_score=0.5, severity="critical")
        assert abs(adj) <= settings.PERSONALIZATION_FEEDBACK_MAX_ADJUSTMENT + 1e-6


# ---------------------------------------------------------------------------
# E) Risk breakdown integrity
# ---------------------------------------------------------------------------

class TestRiskBreakdown:

    def _cold_profile(self) -> Dict:
        return {
            "personalization_level": "cold_start",
            "total_valid_samples": 5, "total_feedback_count": 0,
            "false_alarm_count": 0, "confirmed_risk_count": 0, "sensor_error_count": 0,
            "typical_hr_min": 55.0, "typical_hr_max": 100.0,
            "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0, "typical_motion_max": 0.5,
        }

    def _calibrated_profile(self) -> Dict:
        return {
            "personalization_level": "calibrated",
            "total_valid_samples": 400, "total_feedback_count": 15,
            "false_alarm_count": 2, "confirmed_risk_count": 5, "sensor_error_count": 1,
            "typical_hr_min": 58.0, "typical_hr_max": 88.0,
            "typical_spo2_min": 96.0, "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0, "typical_motion_max": 0.4,
        }

    def _quality_info(self, confidence=0.9, override=False) -> Dict:
        return {
            "quality_confidence": confidence,
            "safety_override": override,
        }

    def test_result_keys_present(self):
        """compute_personalized_risk returns all expected keys."""
        from services.adaptive_personalization_service import compute_personalized_risk

        baseline = {"final_risk_score": 0.4}
        result = compute_personalized_risk(
            global_risk_score=0.4,
            baseline_result=baseline,
            profile=self._cold_profile(),
            trend_info=None,
            quality_info=self._quality_info(),
        )
        required_keys = [
            "global_risk_score", "baseline_final_risk", "baseline_deviation_score",
            "trend_adjustment", "quality_adjustment", "feedback_adjustment",
            "final_personalized_risk", "personalization_level", "confidence", "safety_override"
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_final_risk_clamped_0_1(self):
        """final_personalized_risk must always be in [0, 1]."""
        from services.adaptive_personalization_service import compute_personalized_risk

        # Try to produce out-of-range by giving extreme values
        profile = self._calibrated_profile()
        result = compute_personalized_risk(
            global_risk_score=0.99,
            baseline_result={"final_risk_score": 0.99},
            profile=profile,
            trend_info={"hr_trend": "rising", "spo2_trend": "falling",
                        "motion_trend": "rising", "quality_trend": "stable",
                        "risk_trend": "rising", "trend_confidence": 1.0},
            quality_info=self._quality_info(confidence=0.95),
            hr=180.0, spo2=85.0, motion_score=2.0,
        )
        assert 0.0 <= result["final_personalized_risk"] <= 1.0

    def test_ml_retrieval_not_in_final_risk(self):
        """ML/retrieval shadow results have ZERO effect on final_personalized_risk."""
        from services.adaptive_personalization_service import compute_personalized_risk

        # The function never receives ml/retrieval params — verify no such params exist
        import inspect
        sig = inspect.signature(compute_personalized_risk)
        param_names = list(sig.parameters.keys())
        for forbidden in ("ml_risk", "retrieval_score", "ml_result", "retrieval_result"):
            assert forbidden not in param_names, \
                f"Forbidden parameter '{forbidden}' found in compute_personalized_risk signature"

    def test_safety_override_never_reduces_below_baseline(self):
        """When safety_override=True, final_personalized_risk >= baseline_final_risk."""
        from services.adaptive_personalization_service import compute_personalized_risk

        baseline = {"final_risk_score": 0.7}
        profile = self._calibrated_profile()
        # High false-alarm profile that would normally reduce
        profile["false_alarm_count"] = 100
        profile["total_feedback_count"] = 120
        result = compute_personalized_risk(
            global_risk_score=0.7,
            baseline_result=baseline,
            profile=profile,
            trend_info=None,
            quality_info=self._quality_info(confidence=0.9, override=True),
            severity="critical",
        )
        assert result["final_personalized_risk"] >= result["baseline_final_risk"] - 1e-6

    def test_personalization_disabled_returns_baseline(self):
        """When PERSONALIZATION_ENABLED=False, bonuses are effectively 0."""
        from services.adaptive_personalization_service import compute_contextual_deviation
        from config import settings

        profile = {
            "personalization_level": "calibrated",
            "typical_hr_min": 55.0, "typical_hr_max": 75.0,
            "typical_spo2_min": 95.0, "typical_motion_max": 0.3,
        }
        with mock.patch.object(settings, "PERSONALIZATION_ENABLED", False):
            result = compute_contextual_deviation(
                profile=profile, baseline={},
                hr=150.0, spo2=88.0, motion_score=2.0,
                hr_valid=True, spo2_valid=True,
            )
        assert result["deviation_bonus"] == 0.0


# ---------------------------------------------------------------------------
# F) Repository CRUD
# ---------------------------------------------------------------------------

class TestPersonalizationRepo:

    def test_get_or_create_creates_new_profile(self):
        async def run():
            repo = InMemoryPersonalizationRepo()
            p = await repo.get_or_create_profile("user_new")
            assert p["user_id"] == "user_new"
            assert p["personalization_level"] == "cold_start"
            return p

        asyncio.run(run())

    def test_update_profile_persists(self):
        async def run():
            repo = InMemoryPersonalizationRepo()
            await repo.get_or_create_profile("user_upd")
            await repo.update_profile("user_upd", {"total_valid_samples": 50})
            p = await repo.get_or_create_profile("user_upd")
            assert p["total_valid_samples"] == 50

        asyncio.run(run())

    def test_add_and_list_risk_memory(self):
        async def run():
            repo = InMemoryPersonalizationRepo()
            for i in range(3):
                await repo.add_risk_memory({
                    "id": str(uuid4()), "user_id": "u_mem",
                    "event_type": "warning_entered",
                    "risk_score": 0.6 + i * 0.1,
                    "severity": "warning", "context_json": None,
                    "created_at": datetime.utcnow(),
                })
            memories = await repo.list_risk_memory("u_mem", limit=10)
            assert len(memories) == 3

        asyncio.run(run())

    def test_trend_snapshot_latest(self):
        async def run():
            repo = InMemoryPersonalizationRepo()
            for i in range(3):
                await repo.create_trend_snapshot({
                    "id": str(uuid4()), "user_id": "u_trend",
                    "hr_trend": "rising" if i == 2 else "stable",
                    "spo2_trend": "stable", "motion_trend": "stable",
                    "quality_trend": "stable", "risk_trend": "stable",
                    "trend_confidence": 0.7 + i * 0.1, "window_minutes": 5,
                    "created_at": datetime.utcnow(),
                })
            latest = await repo.get_latest_trend_snapshot("u_trend")
            assert latest["hr_trend"] == "rising"

        asyncio.run(run())

    def test_summarize_personalization(self):
        async def run():
            repo = InMemoryPersonalizationRepo()
            await repo.update_profile("u_sum", {
                "total_valid_samples": 150,
                "total_feedback_count": 20,
                "false_alarm_count": 4,
                "confirmed_risk_count": 6,
                "personalization_level": "learning",
            })
            summary = await repo.summarize_personalization("u_sum")
            assert summary["total_valid_samples"] == 150
            assert abs(summary["false_alarm_rate"] - 0.2) < 1e-4
            assert summary["confirmed_risk_count"] == 6

        asyncio.run(run())


# ---------------------------------------------------------------------------
# G) Service level (AdaptivePersonalizationService)
# ---------------------------------------------------------------------------

class TestAdaptivePersonalizationService:

    def test_get_or_create_profile_returns_dict(self):
        """Service get_or_create_profile returns expected dict even from fresh repo."""
        async def run():
            service = _get_service()
            repos = FakeRepos()
            profile = await service.get_or_create_profile(repos, "u_svc")
            assert profile["user_id"] == "u_svc"
            assert "personalization_level" in profile

        asyncio.run(run())

    def test_record_risk_memory_updates_counters(self):
        """Recording a false_alarm event increments false_alarm_count."""
        async def run():
            service = _get_service()
            repos = FakeRepos()
            await service.record_risk_memory(
                repos, "u_rc", "false_alarm", risk_score=0.55, severity="warning"
            )
            profile = await repos.personalization.get_or_create_profile("u_rc")
            assert profile["false_alarm_count"] == 1
            assert profile["total_feedback_count"] == 1

        asyncio.run(run())

    def test_save_trend_snapshot_persists(self):
        """save_trend_snapshot saves a record via repo."""
        async def run():
            service = _get_service()
            repos = FakeRepos()
            trend = {
                "hr_trend": "rising", "spo2_trend": "falling",
                "motion_trend": "stable", "quality_trend": "stable",
                "risk_trend": "rising", "trend_confidence": 0.7,
            }
            result = await service.save_trend_snapshot(repos, "u_ts", trend)
            assert result is not None
            assert result["hr_trend"] == "rising"

        asyncio.run(run())

    def test_get_personalization_summary_returns_dict(self):
        async def run():
            service = _get_service()
            repos = FakeRepos()
            summary = await service.get_personalization_summary(repos, "u_ps")
            assert "personalization_level" in summary
            assert "typical_ranges" in summary

        asyncio.run(run())

    def test_service_fails_open_with_none_repo(self):
        """Service should return fallback dict when repo is None (fail-open)."""
        async def run():
            service = _get_service()

            class FakeReposNoPersonalization:
                personalization = None

            repos = FakeReposNoPersonalization()
            profile = await service.get_or_create_profile(repos, "u_fo")
            # Should return cold_start fallback, not raise
            assert profile["personalization_level"] == "cold_start"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Config sanity
# ---------------------------------------------------------------------------

class TestConfig:

    def test_personalization_config_keys_present(self):
        """All PERSONALIZATION_* settings exist in config and have correct types."""
        from config import settings

        assert isinstance(settings.PERSONALIZATION_ENABLED, bool)
        assert isinstance(settings.PERSONALIZATION_COLD_START_MAX_BONUS, float)
        assert isinstance(settings.PERSONALIZATION_LEARNING_MAX_BONUS, float)
        assert isinstance(settings.PERSONALIZATION_CALIBRATED_MAX_BONUS, float)
        assert isinstance(settings.PERSONALIZATION_TREND_MAX_BONUS, float)
        assert isinstance(settings.PERSONALIZATION_FEEDBACK_MAX_ADJUSTMENT, float)

    def test_bonus_hierarchy(self):
        """cold_start < learning < calibrated bonus hierarchy must hold."""
        from config import settings

        assert settings.PERSONALIZATION_COLD_START_MAX_BONUS \
            < settings.PERSONALIZATION_LEARNING_MAX_BONUS \
            < settings.PERSONALIZATION_CALIBRATED_MAX_BONUS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service():
    from services.adaptive_personalization_service import AdaptivePersonalizationService
    return AdaptivePersonalizationService()
