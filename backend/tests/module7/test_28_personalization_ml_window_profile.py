from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _InMemoryPersonalizationRepo:
    def __init__(self):
        self.profile = {
            "id": str(uuid4()),
            "user_id": "u1",
            "personalization_level": "learning",
            "total_valid_samples": 200,
            "total_feedback_count": 0,
            "false_alarm_count": 0,
            "confirmed_risk_count": 0,
            "sensor_error_count": 0,
            "typical_hr_min": 55.0,
            "typical_hr_max": 100.0,
            "typical_spo2_min": 95.0,
            "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0,
            "typical_motion_max": 0.5,
            "ml_window_count": 0,
            "ml_usable_window_count": 0,
            "ml_evidence_mean": 0.0,
            "ml_evidence_std": 0.0,
            "ml_confidence_mean": 0.0,
            "ml_positive_support_count": 0,
            "ml_personal_disagreement_count": 0,
        }
        self.memories = []

    async def get_or_create_profile(self, _user_id: str):
        return dict(self.profile)

    async def update_profile(self, _user_id: str, updates):
        self.profile.update(updates)
        self.profile["updated_at"] = datetime.utcnow()
        return dict(self.profile)

    async def add_risk_memory(self, data):
        self.memories.append(dict(data))
        return data


class _InMemoryLearningRepo:
    async def create_feedback(self, data):
        return dict(data)

    async def update_window_feedback(self, _window_id: str, _feedback_label: str):
        return {"ok": True}


class _FakeRepos:
    def __init__(self):
        self.personalization = _InMemoryPersonalizationRepo()
        self.learning = _InMemoryLearningRepo()


class TestPersonalizationMLWindowProfile:
    def test_model_window_updates_profile_counters_and_stats(self):
        from services.adaptive_personalization_service import (
            adaptive_personalization_service,
        )

        async def run():
            repos = _FakeRepos()
            ml_evidence = {
                "ml_evidence_score": 0.72,
                "ml_confidence": 0.82,
                "ml_usable": True,
            }
            fusion = {
                "personalized_risk_score": 0.40,
                "ml_adjustment": 0.08,
                "final_risk_score": 0.48,
            }
            updated = await adaptive_personalization_service.update_profile_from_ml_window(
                repos=repos,
                user_id="u1",
                ml_evidence_result=ml_evidence,
                fusion_result=fusion,
                window_quality={"model_ready": True},
            )
            assert updated["ml_window_count"] == 1
            assert updated["ml_usable_window_count"] == 1
            assert updated["ml_evidence_mean"] > 0
            assert "last_model_window_at" in updated

        asyncio.run(run())

    def test_disagreement_count_increments_for_large_delta(self):
        from services.adaptive_personalization_service import (
            adaptive_personalization_service,
        )

        async def run():
            repos = _FakeRepos()
            ml_evidence = {
                "ml_evidence_score": 0.95,
                "ml_confidence": 0.90,
                "ml_usable": True,
            }
            fusion = {
                "personalized_risk_score": 0.20,
                "ml_adjustment": 0.15,
                "final_risk_score": 0.35,
            }
            updated = await adaptive_personalization_service.update_profile_from_ml_window(
                repos=repos,
                user_id="u1",
                ml_evidence_result=ml_evidence,
                fusion_result=fusion,
                window_quality={"model_ready": True},
            )
            assert updated["ml_personal_disagreement_count"] >= 1

        asyncio.run(run())

    def test_feedback_links_into_personalization_memory(self):
        from services.learning_data_service import learning_data_service

        async def run():
            repos = _FakeRepos()
            await learning_data_service.attach_feedback(
                repos=repos,
                user_id="u1",
                related_window_id="w123",
                related_alert_id="a123",
                feedback_type="false_alarm",
                feedback_source="mobile",
                note="test",
            )
            assert len(repos.personalization.memories) == 1
            ctx = repos.personalization.memories[0].get("context_json") or {}
            assert ctx.get("related_window_id") == "w123"

        asyncio.run(run())

    def test_existing_personalization_compute_still_works(self):
        from services.adaptive_personalization_service import compute_personalized_risk

        profile = {
            "personalization_level": "learning",
            "total_valid_samples": 120,
            "total_feedback_count": 4,
            "false_alarm_count": 1,
            "confirmed_risk_count": 1,
            "sensor_error_count": 0,
            "typical_hr_min": 55.0,
            "typical_hr_max": 100.0,
            "typical_spo2_min": 95.0,
            "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0,
            "typical_motion_max": 0.5,
        }
        out = compute_personalized_risk(
            global_risk_score=0.4,
            baseline_result={"final_risk_score": 0.4},
            profile=profile,
            trend_info=None,
            quality_info={"quality_confidence": 0.9, "safety_override": False},
        )
        assert 0.0 <= out["final_personalized_risk"] <= 1.0
