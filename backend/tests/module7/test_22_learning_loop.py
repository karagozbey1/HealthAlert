"""Test 22 — Part 5A: Learning Loop & Training Data Intelligence Layer

Tests:
  A) Capture decision logic
     - Normal low-risk packets are sampled probabilistically
     - Warning/critical events are always captured
     - Low quality packets get training_candidate=False
     - Mock/demo packets get training_candidate=False

  B) Label suggestion
     - final_risk_score is never modified
     - ML/retrieval shadow added as metadata only
     - Correct suggested_label from heuristic level

  C) Feedback handling
     - false_alarm feedback is saved and linked to window
     - sensor_error feedback sets training_candidate=False
     - Feedback stored with correct fields

  D) Export
     - user_id and device_id are anonymised (hashed)
     - Only training_candidate=True windows are exported
     - sensor_error windows excluded from export
     - Export produces windows.jsonl, feedback.jsonl, export_summary.json

  E) Service isolation
     - Learning service failure does not raise from ingestion (fail-open)
     - final_risk_score unchanged after learning capture

  F) Repository & config
     - Model version registry lists correctly
     - Config keys present and correct types
     - LEARNING_LOOP_ENABLED=False disables capture

  G) Shadow result isolation
     - ML shadow result NOT in learning window keys that affect risk
     - Retrieval shadow result stored only as summary metadata
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
import unittest.mock as mock
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_learning.db")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_packet(**overrides):
    base = dict(
        device_id="ha-esp32-001",
        timestamp_ms=1_700_000_000_000,
        mode="real",
        packet_seq=5001,
        accel_x=0.01, accel_y=0.02, accel_z=1.0,
        gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
        red_value=50_000, ir_value=55_000,
        heart_rate=72.0, spo2=98.0, signal_quality=0.9,
        imu_ok=True, ppg_ok=True,
        hr_valid=True, spo2_valid=True, finger_detected=True,
        state_hint="normal",
    )
    base.update(overrides)
    return base


def _fake_risk_breakdown(risk_score=0.05, quality_confidence=0.9, baseline_ready=True):
    return {
        "final_risk_score": risk_score,
        "global_risk_score": risk_score,
        "quality_confidence": quality_confidence,
        "baseline_ready": baseline_ready,
        "personal_bonus": 0.0,
        "sensitivity_offset": 0.0,
    }


def _fake_ml_shadow(risk_level="normal", skipped=False):
    if skipped:
        return {"ml_skipped": True, "shadow_mode": True}
    return {
        "ml_final_risk_level": risk_level,
        "ml_risk_score": 0.1,
        "shadow_mode": True,
        "ml_skipped": False,
        "inference_latency_ms": 12.0,
    }


def _fake_retrieval_shadow(support=0.8, skipped=False):
    if skipped:
        return {"retrieval_skipped": True, "shadow_mode": True}
    return {
        "support_score": support,
        "retrieval_skipped": False,
        "low_confidence": False,
        "shadow_mode": True,
        "top_k_labels": ["normal", "normal", "watch"],
    }


# ---------------------------------------------------------------------------
# In-memory learning repo for tests
# ---------------------------------------------------------------------------

class InMemoryLearningRepo:
    def __init__(self):
        self._windows: Dict[str, Dict] = {}
        self._feedback: Dict[str, Dict] = {}
        self._model_versions: Dict[str, Dict] = {}

    async def create_session(self, data): return data
    async def close_session(self, session_id, ended_at): return None

    async def create_window(self, data):
        w = dict(data)
        if isinstance(w.get("ml_shadow_summary"), dict):
            pass  # keep as-is
        self._windows[w["id"]] = w
        return w

    async def list_windows(self, user_id=None, training_candidate=None, source=None, limit=100):
        rows = list(self._windows.values())
        if user_id:
            rows = [r for r in rows if r["user_id"] == user_id]
        if training_candidate is not None:
            rows = [r for r in rows if r["training_candidate"] == training_candidate]
        if source:
            rows = [r for r in rows if r["source"] == source]
        return rows[:limit]

    async def get_window(self, window_id):
        return self._windows.get(window_id)

    async def mark_window_candidate(self, window_id, status):
        w = self._windows.get(window_id)
        if w:
            w["training_candidate"] = status in ("candidate", "approved")
        return w

    async def update_window_feedback(self, window_id, feedback_label):
        w = self._windows.get(window_id)
        if w:
            w["user_feedback_label"] = feedback_label
            if feedback_label == "sensor_error":
                w["training_candidate"] = False
        return w

    async def create_feedback(self, data):
        f = dict(data)
        self._feedback[f["id"]] = f
        return f

    async def get_feedback_for_window(self, window_id):
        return [f for f in self._feedback.values() if f.get("related_window_id") == window_id]

    async def create_model_version(self, data):
        m = dict(data)
        self._model_versions[m["id"]] = m
        return m

    async def list_model_versions(self):
        return list(self._model_versions.values())

    async def get_active_model_version(self):
        active = [m for m in self._model_versions.values() if m.get("status") == "active"]
        return active[0] if active else None

    async def list_windows_for_export(self, user_id=None, include_demo=False,
                                       min_quality_confidence=0.0, limit=1000):
        rows = [
            w for w in self._windows.values()
            if w.get("training_candidate")
            and w.get("exported_at") is None
            and w.get("quality_confidence", 1.0) >= min_quality_confidence
        ]
        if user_id:
            rows = [r for r in rows if r["user_id"] == user_id]
        if not include_demo:
            rows = [r for r in rows if r.get("source") != "demo"]
        return rows[:limit]

    async def mark_windows_exported(self, window_ids):
        for wid in window_ids:
            if wid in self._windows:
                self._windows[wid]["exported_at"] = datetime.utcnow()
        return len(window_ids)


class FakeRepos:
    def __init__(self):
        self.learning = InMemoryLearningRepo()


# ---------------------------------------------------------------------------
# A) Capture decision logic
# ---------------------------------------------------------------------------

class TestCaptureDecision:

    def test_normal_rate_sampling(self):
        """should_capture_window respects LEARNING_CAPTURE_NORMAL_RATE sampling."""
        from services.learning_data_service import should_capture_window
        from config import settings

        with mock.patch.object(settings, "LEARNING_LOOP_ENABLED", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_NORMAL_RATE", 0.0), \
             mock.patch.object(settings, "LEARNING_CAPTURE_WARNING_ALWAYS", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_CRITICAL_ALWAYS", True):
            # With rate=0.0 and normal level, should never capture
            results = [
                should_capture_window(
                    user_id="u1", packet_mode="real",
                    final_risk_score=0.05, quality_confidence=0.9,
                    risk_level=None, baseline_ready=True,
                )
                for _ in range(20)
            ]
        assert not any(results), "Normal rate=0.0 should capture nothing"

    def test_warning_always_captured(self):
        """Warning events are always captured regardless of rate."""
        from services.learning_data_service import should_capture_window
        from config import settings

        with mock.patch.object(settings, "LEARNING_LOOP_ENABLED", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_NORMAL_RATE", 0.0), \
             mock.patch.object(settings, "LEARNING_CAPTURE_WARNING_ALWAYS", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_CRITICAL_ALWAYS", True):
            result = should_capture_window(
                user_id="u1", packet_mode="real",
                final_risk_score=0.6, quality_confidence=0.9,
                risk_level="warning", baseline_ready=True,
            )
        assert result is True

    def test_critical_always_captured(self):
        """Critical events are always captured regardless of rate."""
        from services.learning_data_service import should_capture_window
        from config import settings

        with mock.patch.object(settings, "LEARNING_LOOP_ENABLED", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_NORMAL_RATE", 0.0), \
             mock.patch.object(settings, "LEARNING_CAPTURE_WARNING_ALWAYS", True), \
             mock.patch.object(settings, "LEARNING_CAPTURE_CRITICAL_ALWAYS", True):
            result = should_capture_window(
                user_id="u1", packet_mode="real",
                final_risk_score=0.85, quality_confidence=0.9,
                risk_level="critical", baseline_ready=True,
            )
        assert result is True

    def test_loop_disabled_never_captures(self):
        """When LEARNING_LOOP_ENABLED=False, should_capture_window always returns False."""
        from services.learning_data_service import should_capture_window
        from config import settings

        with mock.patch.object(settings, "LEARNING_LOOP_ENABLED", False):
            for level in (None, "watch", "warning", "critical"):
                assert not should_capture_window(
                    user_id="u1", packet_mode="real",
                    final_risk_score=0.9, quality_confidence=0.95,
                    risk_level=level, baseline_ready=True,
                )


# ---------------------------------------------------------------------------
# B) Window building & label suggestion
# ---------------------------------------------------------------------------

class TestWindowBuilding:

    def test_build_window_does_not_change_risk_score(self):
        """build_and_save_window must not modify final_risk_score."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()
        original_score = 0.35

        result = asyncio.run(svc.build_and_save_window(
            repos=repos,
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=original_score,
            quality_confidence=0.85,
            risk_level="watch",
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(original_score),
            window_status={"current_size": 150},
            ml_shadow_result=_fake_ml_shadow("watch"),
            retrieval_shadow_result=_fake_retrieval_shadow(),
        ))

        assert result is not None
        assert result["captured"] is True
        window_id = result["window_id"]
        saved_window = repos.learning._windows[window_id]
        # final_risk_score stored in window must match original
        assert saved_window["final_risk_score"] == original_score

    def test_low_quality_window_not_candidate(self):
        """Windows with quality_confidence below threshold get training_candidate=False."""
        from services.learning_data_service import LearningDataService
        from config import settings
        svc = LearningDataService()
        repos = FakeRepos()

        with mock.patch.object(settings, "LEARNING_MIN_QUALITY_CONFIDENCE", 0.60):
            result = asyncio.run(svc.build_and_save_window(
                repos=repos,
                user_id="u1",
                device_id="dev1",
                packet_mode="real",
                final_risk_score=0.8,
                quality_confidence=0.40,  # below threshold
                risk_level="critical",
                baseline_ready=True,
                risk_breakdown=_fake_risk_breakdown(0.8, quality_confidence=0.40),
                window_status=None,
                ml_shadow_result=None,
                retrieval_shadow_result=None,
            ))

        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        assert saved["training_candidate"] is False, "Low quality must not be training candidate"

    def test_demo_packet_not_candidate_by_default(self):
        """Mock/demo packets produce training_candidate=False unless ALLOW_DEMO=True."""
        from services.learning_data_service import LearningDataService
        from config import settings
        svc = LearningDataService()
        repos = FakeRepos()

        with mock.patch.object(settings, "LEARNING_ALLOW_DEMO_AS_TRAINING", False):
            result = asyncio.run(svc.build_and_save_window(
                repos=repos,
                user_id="u1",
                device_id="dev1",
                packet_mode="mock",  # demo source
                final_risk_score=0.1,
                quality_confidence=0.9,
                risk_level=None,
                baseline_ready=True,
                risk_breakdown=_fake_risk_breakdown(0.1),
                window_status=None,
                ml_shadow_result=None,
                retrieval_shadow_result=None,
            ))

        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        assert saved["training_candidate"] is False, "Demo packet must not be training candidate"
        assert saved["source"] == "demo"

    def test_ml_shadow_stored_as_summary_only(self):
        """ML shadow result is stored only as summary metadata, not as a risk driver."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        ml_result = _fake_ml_shadow("critical")
        result = asyncio.run(svc.build_and_save_window(
            repos=repos,
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=0.2,  # heuristic says low risk
            quality_confidence=0.9,
            risk_level=None,
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(0.2),
            window_status=None,
            ml_shadow_result=ml_result,
            retrieval_shadow_result=None,
        ))

        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        # final_risk_score must be unchanged (heuristic value)
        assert saved["final_risk_score"] == 0.2
        # ml_shadow_summary is present but does not override risk
        assert saved["ml_shadow_summary"] is not None
        assert "final_risk_score" not in saved["ml_shadow_summary"], \
            "ML summary must not contain final_risk_score field"

    def test_suggest_label_normal(self):
        """suggest_label returns 'normal' for low-risk, no feedback."""
        from services.learning_data_service import suggest_label
        result = suggest_label(
            final_risk_score=0.1,
            risk_level=None,
            risk_breakdown=_fake_risk_breakdown(0.1),
            ml_shadow_result=None,
            retrieval_shadow_result=None,
        )
        assert result["suggested_label"] == "normal"

    def test_suggest_label_critical(self):
        """suggest_label returns 'critical' for critical risk level."""
        from services.learning_data_service import suggest_label
        result = suggest_label(
            final_risk_score=0.85,
            risk_level="critical",
            risk_breakdown=_fake_risk_breakdown(0.85),
            ml_shadow_result=None,
            retrieval_shadow_result=None,
        )
        assert result["suggested_label"] == "critical"

    def test_suggest_label_user_feedback_overrides(self):
        """User feedback (false_alarm) overrides automated label."""
        from services.learning_data_service import suggest_label
        result = suggest_label(
            final_risk_score=0.8,
            risk_level="critical",
            risk_breakdown=_fake_risk_breakdown(0.8),
            ml_shadow_result=None,
            retrieval_shadow_result=None,
            user_feedback="false_alarm",
        )
        assert result["suggested_label"] == "normal"
        assert result["label_confidence"] >= 0.8


# ---------------------------------------------------------------------------
# C) Feedback handling
# ---------------------------------------------------------------------------

class TestFeedbackHandling:

    def test_false_alarm_feedback_saved_and_linked(self):
        """false_alarm feedback is saved and linked to the window."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        # First create a window
        window_id = str(uuid4())
        repos.learning._windows[window_id] = {
            "id": window_id,
            "user_id": "u1",
            "training_candidate": True,
            "user_feedback_label": None,
            "quality_confidence": 0.9,
            "exported_at": None,
        }

        saved = asyncio.run(svc.attach_feedback(
            repos=repos,
            user_id="u1",
            related_window_id=window_id,
            related_alert_id=None,
            feedback_type="false_alarm",
            feedback_source="mobile",
            note="I felt fine",
        ))

        assert saved["feedback_type"] == "false_alarm"
        assert saved["user_id"] == "u1"
        assert saved["related_window_id"] == window_id
        # Window feedback label updated
        assert repos.learning._windows[window_id]["user_feedback_label"] == "false_alarm"
        # false_alarm does NOT disqualify window from training
        assert repos.learning._windows[window_id]["training_candidate"] is True

    def test_sensor_error_feedback_excludes_from_training(self):
        """sensor_error feedback sets window training_candidate=False."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        window_id = str(uuid4())
        repos.learning._windows[window_id] = {
            "id": window_id,
            "user_id": "u1",
            "training_candidate": True,
            "user_feedback_label": None,
            "quality_confidence": 0.9,
            "exported_at": None,
        }

        asyncio.run(svc.attach_feedback(
            repos=repos,
            user_id="u1",
            related_window_id=window_id,
            related_alert_id=None,
            feedback_type="sensor_error",
            feedback_source="mobile",
            note=None,
        ))

        assert repos.learning._windows[window_id]["user_feedback_label"] == "sensor_error"
        assert repos.learning._windows[window_id]["training_candidate"] is False, \
            "sensor_error must exclude window from training"


# ---------------------------------------------------------------------------
# D) Export
# ---------------------------------------------------------------------------

class TestExport:

    def test_export_anonymises_user_device_ids(self, tmp_path):
        """Export JSONL must not contain raw user_id or device_id."""
        from services.learning_data_service import LearningDataService, _anon_id
        from config import settings
        svc = LearningDataService()
        repos = FakeRepos()

        real_user_id = "user-abc-123"
        real_device_id = "device-xyz-456"

        window_id = str(uuid4())
        repos.learning._windows[window_id] = {
            "id": window_id,
            "user_id": real_user_id,
            "device_id": real_device_id,
            "training_candidate": True,
            "exported_at": None,
            "quality_confidence": 0.9,
            "source": "live",
            "window_start_at": datetime.utcnow(),
            "duration_sec": 30.0,
            "risk_level_at_capture": "normal",
            "final_risk_score": 0.1,
            "baseline_ready": True,
            "ml_shadow_summary": None,
            "retrieval_shadow_summary": None,
            "user_feedback_label": None,
            "suggested_label": "normal",
            "label_confidence": 0.6,
        }

        with mock.patch.object(settings, "LEARNING_EXPORT_DIR", str(tmp_path)), \
             mock.patch.object(settings, "LEARNING_MIN_QUALITY_CONFIDENCE", 0.0):
            summary = asyncio.run(svc.export_training_dataset(repos=repos, include_demo=False))

        export_dir = summary["export_dir"]
        windows_file = os.path.join(export_dir, "windows.jsonl")
        assert os.path.exists(windows_file), "windows.jsonl must exist"

        with open(windows_file, encoding="utf-8") as f:
            row = json.loads(f.readline())

        assert row["user_id_hash"] != real_user_id, "user_id must be anonymised"
        assert row["device_id_hash"] != real_device_id, "device_id must be anonymised"
        assert row["user_id_hash"] == _anon_id(real_user_id)
        assert "user_id" not in row, "raw user_id must not appear in export"

    def test_export_excludes_sensor_error_windows(self, tmp_path):
        """Windows with sensor_error feedback (training_candidate=False) not exported."""
        from services.learning_data_service import LearningDataService
        from config import settings
        svc = LearningDataService()
        repos = FakeRepos()

        for i, (candidate, label) in enumerate([
            (True, "false_alarm"),
            (False, "sensor_error"),
        ]):
            wid = str(uuid4())
            repos.learning._windows[wid] = {
                "id": wid,
                "user_id": "u1",
                "device_id": "dev1",
                "training_candidate": candidate,
                "exported_at": None,
                "quality_confidence": 0.9,
                "source": "live",
                "window_start_at": datetime.utcnow(),
                "duration_sec": 30.0,
                "risk_level_at_capture": "warning",
                "final_risk_score": 0.6,
                "baseline_ready": True,
                "ml_shadow_summary": None,
                "retrieval_shadow_summary": None,
                "user_feedback_label": label,
                "suggested_label": "warning",
                "label_confidence": 0.7,
            }

        with mock.patch.object(settings, "LEARNING_EXPORT_DIR", str(tmp_path)), \
             mock.patch.object(settings, "LEARNING_MIN_QUALITY_CONFIDENCE", 0.0):
            summary = asyncio.run(svc.export_training_dataset(repos=repos, include_demo=False))

        assert summary["window_count"] == 1, "Only 1 candidate window should export"

    def test_export_creates_required_files(self, tmp_path):
        """Export creates windows.jsonl, feedback.jsonl, export_summary.json."""
        from services.learning_data_service import LearningDataService
        from config import settings
        svc = LearningDataService()
        repos = FakeRepos()

        with mock.patch.object(settings, "LEARNING_EXPORT_DIR", str(tmp_path)), \
             mock.patch.object(settings, "LEARNING_MIN_QUALITY_CONFIDENCE", 0.0):
            summary = asyncio.run(svc.export_training_dataset(repos=repos, include_demo=False))

        export_dir = summary["export_dir"]
        assert os.path.exists(os.path.join(export_dir, "windows.jsonl"))
        assert os.path.exists(os.path.join(export_dir, "feedback.jsonl"))
        assert os.path.exists(os.path.join(export_dir, "export_summary.json"))


# ---------------------------------------------------------------------------
# E) Service isolation (fail-open)
# ---------------------------------------------------------------------------

class TestServiceIsolation:

    def test_learning_service_error_returns_none_not_raises(self):
        """If the repo raises, build_and_save_window returns None (fail-open)."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()

        class BrokenRepo:
            async def create_window(self, data):
                raise RuntimeError("DB is down")

        class BrokenRepos:
            learning = BrokenRepo()

        result = asyncio.run(svc.build_and_save_window(
            repos=BrokenRepos(),
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=0.9,
            quality_confidence=0.9,
            risk_level="critical",
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(0.9),
            window_status=None,
            ml_shadow_result=None,
            retrieval_shadow_result=None,
        ))

        assert result is None, "Learning failure must not raise — must return None"

    def test_final_risk_score_unchanged_after_learning_capture(self):
        """Verified: final_risk_score is the same before and after learning capture."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        original = 0.72

        result = asyncio.run(svc.build_and_save_window(
            repos=repos,
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=original,
            quality_confidence=0.9,
            risk_level="warning",
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(original),
            window_status={"current_size": 100},
            ml_shadow_result=_fake_ml_shadow("critical"),  # ML says critical
            retrieval_shadow_result=_fake_retrieval_shadow(),
        ))

        # final_risk_score in the saved window must match the input value
        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        assert saved["final_risk_score"] == original, \
            "Learning loop must NOT modify final_risk_score"


# ---------------------------------------------------------------------------
# F) Repository & config
# ---------------------------------------------------------------------------

class TestRepoAndConfig:

    def test_model_version_registry_lists(self):
        """Model version registry stores and retrieves entries."""
        repos = FakeRepos()
        mv_data = {
            "id": str(uuid4()),
            "model_name": "fusion_v1",
            "version": "1.0.0",
            "model_path": "outputs/models/best.pt",
            "training_data_snapshot": None,
            "metrics_json": None,
            "status": "candidate",
            "created_at": datetime.utcnow(),
            "activated_at": None,
        }
        asyncio.run(repos.learning.create_model_version(mv_data))
        versions = asyncio.run(repos.learning.list_model_versions())
        assert len(versions) == 1
        assert versions[0]["model_name"] == "fusion_v1"
        assert versions[0]["status"] == "candidate"

    def test_config_learning_keys_present(self):
        """All Part 5A config keys are present with correct types."""
        from config import settings
        assert isinstance(settings.LEARNING_LOOP_ENABLED, bool)
        assert isinstance(settings.LEARNING_CAPTURE_NORMAL_RATE, float)
        assert isinstance(settings.LEARNING_CAPTURE_WARNING_ALWAYS, bool)
        assert isinstance(settings.LEARNING_CAPTURE_CRITICAL_ALWAYS, bool)
        assert isinstance(settings.LEARNING_ALLOW_DEMO_AS_TRAINING, bool)
        assert isinstance(settings.LEARNING_EXPORT_DIR, str)
        assert isinstance(settings.LEARNING_MIN_QUALITY_CONFIDENCE, float)
        assert 0.0 <= settings.LEARNING_CAPTURE_NORMAL_RATE <= 1.0
        assert 0.0 <= settings.LEARNING_MIN_QUALITY_CONFIDENCE <= 1.0

    def test_loop_disabled_flag_disables_capture(self):
        """LEARNING_LOOP_ENABLED=False disables all capture."""
        from services.learning_data_service import should_capture_window
        from config import settings
        with mock.patch.object(settings, "LEARNING_LOOP_ENABLED", False):
            assert not should_capture_window(
                user_id="u1", packet_mode="real",
                final_risk_score=1.0, quality_confidence=1.0,
                risk_level="critical", baseline_ready=True,
            )


# ---------------------------------------------------------------------------
# G) Shadow result isolation
# ---------------------------------------------------------------------------

class TestShadowResultIsolation:

    def test_ml_shadow_summary_has_no_final_risk_score_key(self):
        """ml_shadow_summary stored in window must not include 'final_risk_score'."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        # ML result that would try to influence risk (shadow mode should prevent this)
        ml_result = {
            "ml_final_risk_level": "critical",
            "ml_risk_score": 0.95,
            "final_risk_score": 0.95,   # this must NOT pass through to window risk fields
            "shadow_mode": True,
            "ml_skipped": False,
            "inference_latency_ms": 10.0,
        }

        result = asyncio.run(svc.build_and_save_window(
            repos=repos,
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=0.15,    # heuristic score (low)
            quality_confidence=0.9,
            risk_level=None,
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(0.15),
            window_status=None,
            ml_shadow_result=ml_result,
            retrieval_shadow_result=None,
        ))

        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        assert saved["final_risk_score"] == 0.15, "Heuristic score must be used"
        ml_summary = saved.get("ml_shadow_summary") or {}
        assert "final_risk_score" not in ml_summary, \
            "final_risk_score must not leak into ml_shadow_summary"

    def test_retrieval_shadow_stored_as_metadata_only(self):
        """Retrieval result stored as summary only; never overrides risk score."""
        from services.learning_data_service import LearningDataService
        svc = LearningDataService()
        repos = FakeRepos()

        retrieval_result = _fake_retrieval_shadow(support=0.95)
        # Add a key that should NOT influence risk
        retrieval_result["final_risk_score"] = 0.9

        result = asyncio.run(svc.build_and_save_window(
            repos=repos,
            user_id="u1",
            device_id="dev1",
            packet_mode="real",
            final_risk_score=0.05,
            quality_confidence=0.9,
            risk_level=None,
            baseline_ready=True,
            risk_breakdown=_fake_risk_breakdown(0.05),
            window_status=None,
            ml_shadow_result=None,
            retrieval_shadow_result=retrieval_result,
        ))

        assert result is not None
        saved = repos.learning._windows[result["window_id"]]
        assert saved["final_risk_score"] == 0.05
        retr_summary = saved.get("retrieval_shadow_summary") or {}
        assert "final_risk_score" not in retr_summary, \
            "final_risk_score must not leak into retrieval_shadow_summary"
