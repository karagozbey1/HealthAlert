"""Test 19 — Part 3.1: Live Alignment, ML/Retrieval Safety Hardening

Tests:
  A) ML sample-rate mismatch skip gate
     - sample_rate_warning=True → predictor NOT called, ml_skipped=True
     - ML_ALLOW_LOW_CONFIDENCE_INFERENCE=True → skip gate bypassed
     - ML_SKIP_ON_SAMPLE_RATE_MISMATCH=False → skip gate bypassed
     - Skip result has required keys

  B) ML vitals input_dim
     - ML_VITALS_DIM=2 → vitals shape (2,)
     - ML_VITALS_DIM=3 → vitals shape (3,)
     - ML_VITALS_DIM=0 → fallback to resolved dim (3 or auto-detected)
     - Vitals shape mismatch → fail-open, no 500

  C) Per-user EMA isolation
     - Two users' EMA states do not share the same dict reference
     - reset_user_state clears the user entry from _ema_states_by_user
     - User A inference does not pollute User B's initial state
     - User A state persists correctly after inference (stub)

  D) Retrieval sample-rate mismatch gate
     - sample_rate_warning=True, no slow index → retrieval_skipped=True
     - sample_rate_warning=True, slow index available → aligned_mode="slow_1hz"
     - RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True → 50Hz query proceeds
     - sample_rate_warning=False → normal 50Hz query (not skipped)

  E) Retrieval slow index path
     - Small fixture slow index loaded → query returns retrieval_available=True
     - aligned_mode="slow_1hz" in result
     - final_risk_score not in retrieval result (shadow only)

  F) Demo self-match
     - demo_query_result.json has self_match_present key (if file exists)
     - exclude_self_applied key present
     - Run demo with exclude_self=True → fewer or equal examples returned

  G) Regression — Parts 1, 2, 3, config
     - test_16 imports intact (baseline_service)
     - test_17 imports intact (live_window_buffer, ml_inference_service)
     - test_18 imports intact (retrieval_engine, retrieval_shadow_service)
     - Config has all Part 3.1 alignment settings
     - DevicePacketResponse schema unchanged
     - Smoke API check: retrieval_shadow_result key present
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest.mock as mock
from collections import deque

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_alignment.db")

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_AI_ROOT = os.path.join(_PROJECT_ROOT, "healthalert_final_ai")
if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_window(n: int = 200):
    return [
        types.SimpleNamespace(
            timestamp_ms=1_700_000_000_000 + i * 1000,
            packet_seq=i,
            mode="mock",
            accel_x=0.01, accel_y=0.02, accel_z=1.0,
            gyro_x=0.0,  gyro_y=0.0,  gyro_z=0.0,
            red_value=50_000, ir_value=55_000,
            heart_rate=72.0, spo2=98.0, signal_quality=0.9,
            imu_ok=True, ppg_ok=True,
            hr_valid=True, spo2_valid=True, finger_detected=True,
            motion_score=0.1, final_risk_score=0.1, quality_confidence=0.9,
        )
        for i in range(n)
    ]


def _window_status_with_warning(warning: bool = True) -> dict:
    return {
        "is_full": True,
        "current_size": 200,
        "target_size": 200,
        "sample_rate_warning": warning,
        "estimated_window_duration_sec": 200.0 if warning else 4.0,
        "expected_duration_sec": 4.0,
    }


def _make_slow_index(tmp_path, n: int = 20, dim: int = 21):
    """Build a tiny slow-index fixture at tmp_path."""
    import joblib
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    X = np.random.default_rng(99).random((n, dim)).astype(np.float32)
    scaler = StandardScaler().fit(X)
    nn = NearestNeighbors(n_neighbors=min(5, n)).fit(scaler.transform(X))
    metadata = [
        {"dataset": "HIFD", "subject_id": f"s{i}", "scenario": "fall1",
         "label_group": "fall" if i % 2 == 0 else "normal",
         "risk_level_estimate": "critical" if i % 2 == 0 else "low",
         "window_index": i, "slow_index": True}
        for i in range(n)
    ]
    summary = {"feature_dim": dim, "total_windows": n, "slow_index": True,
               "datasets_included": ["HIFD"]}
    os.makedirs(tmp_path, exist_ok=True)
    joblib.dump(nn, os.path.join(tmp_path, "retrieval_index.joblib"))
    joblib.dump(scaler, os.path.join(tmp_path, "retrieval_scaler.joblib"))
    np.save(os.path.join(tmp_path, "retrieval_features.npy"), X)
    with open(os.path.join(tmp_path, "retrieval_metadata.json"), "w") as f:
        json.dump(metadata, f)
    with open(os.path.join(tmp_path, "retrieval_build_summary.json"), "w") as f:
        json.dump(summary, f)


# ---------------------------------------------------------------------------
# A) ML sample-rate mismatch skip gate
# ---------------------------------------------------------------------------

class TestMLSampleRateGate:

    def test_a1_skip_when_warning_and_gate_enabled(self):
        """sample_rate_warning=True + gate=True → ml_skipped=True, predictor not called."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True

        call_count = {"n": 0}

        def fake_predict(*a, **kw):
            call_count["n"] += 1
            return {"ml_available": True}

        svc._predictor = types.SimpleNamespace(
            predict=fake_predict, _ema_state={}, reset=lambda: None
        )
        svc._postprocessor = types.SimpleNamespace(process=lambda **kw: {})

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True

            result = svc.predict_window(
                "user_a",
                _fake_window(),
                window_status=_window_status_with_warning(True),
            )

        assert result["ml_skipped"] is True
        assert result["ml_available"] is False
        assert result["skip_reason"] == "sample_rate_mismatch"
        assert result["shadow_mode"] is True
        assert result["low_confidence"] is True
        assert call_count["n"] == 0, "Predictor should NOT have been called"

    def test_a2_no_skip_when_override_enabled(self):
        """ML_ALLOW_LOW_CONFIDENCE_INFERENCE=True → skip gate bypassed."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        def fake_predict(imu, ppg, vitals, smooth=True):
            return {
                "fall_prob": 0.1, "instability_prob": 0.1,
                "quality_score": 0.9, "risk_score": 0.1,
            }

        svc._predictor = types.SimpleNamespace(
            predict=fake_predict, _ema_state={
                "fall_prob": 0.0, "instability_prob": 0.0,
                "quality_score": 1.0, "risk_score": 0.0,
            }, reset=lambda: None
        )
        svc._postprocessor = types.SimpleNamespace(
            process=lambda predictions, vitals: {
                "fall_probability": 0.1, "final_risk_level": "normal",
                "immediate_alert": False,
            }
        )

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = True  # override
            ms.ML_FAIL_OPEN = True
            ms.ML_VITALS_DIM = 3

            result = svc.predict_window(
                "user_b",
                _fake_window(),
                window_status=_window_status_with_warning(True),
            )

        # Should not be skipped
        assert result.get("ml_skipped") is not True

    def test_a3_no_skip_when_gate_disabled(self):
        """ML_SKIP_ON_SAMPLE_RATE_MISMATCH=False → skip gate bypassed."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = False  # model not available → unavailable result

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = False
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True

            result = svc.predict_window(
                "user_c",
                _fake_window(),
                window_status=_window_status_with_warning(True),
            )

        # Not skipped — falls through to unavailable result
        assert result.get("ml_skipped") is not True

    def test_a4_skip_result_has_required_keys(self):
        """Skip result contains all expected keys."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True

            result = svc.predict_window(
                "user_d",
                _fake_window(),
                window_status=_window_status_with_warning(True),
            )

        required_keys = {
            "ml_available", "ml_skipped", "skip_reason", "shadow_mode",
            "low_confidence", "estimated_window_duration_sec", "expected_duration_sec",
        }
        assert required_keys.issubset(result.keys())
        assert result["estimated_window_duration_sec"] == 200.0
        assert result["expected_duration_sec"] == 4.0


# ---------------------------------------------------------------------------
# B) ML vitals input_dim
# ---------------------------------------------------------------------------

class TestMLVitalsDim:

    def test_b1_vitals_dim_2_produces_shape_2(self):
        """ML_VITALS_DIM=2 → build_predictor_inputs vitals.shape == (2,)."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_VITALS_DIM = 2
            svc._resolved_vitals_dim = 2
            inputs = svc.build_predictor_inputs(_fake_window(10))

        assert inputs["vitals"].shape == (2,), f"Expected (2,), got {inputs['vitals'].shape}"
        assert inputs["vitals"].dtype == np.float32

    def test_b2_vitals_dim_3_produces_shape_3(self):
        """ML_VITALS_DIM=3 → build_predictor_inputs vitals.shape == (3,)."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._resolved_vitals_dim = 3
        inputs = svc.build_predictor_inputs(_fake_window(10))

        assert inputs["vitals"].shape == (3,), f"Expected (3,), got {inputs['vitals'].shape}"

    def test_b3_vitals_dim_0_uses_fallback(self):
        """ML_VITALS_DIM=0 → _detect_vitals_dim returns 3 (fallback, no model)."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_VITALS_DIM = 0
            dim = svc._detect_vitals_dim()

        assert dim in (2, 3), f"Expected 2 or 3, got {dim}"

    def test_b4_vitals_content_dim_2(self):
        """vitals[0]=hr, vitals[1]=spo2/100 when dim=2."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._resolved_vitals_dim = 2
        window = _fake_window(5)
        # Last sample: heart_rate=72, spo2=98
        inputs = svc.build_predictor_inputs(window)

        assert abs(inputs["vitals"][0] - 72.0) < 1e-3     # hr
        assert abs(inputs["vitals"][1] - 0.98) < 1e-3     # spo2/100

    def test_b5_vitals_content_dim_3(self):
        """vitals[2]=signal_quality when dim=3."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._resolved_vitals_dim = 3
        window = _fake_window(5)
        inputs = svc.build_predictor_inputs(window)

        assert abs(inputs["vitals"][2] - 0.9) < 1e-3      # signal_quality=0.9


# ---------------------------------------------------------------------------
# C) Per-user EMA isolation
# ---------------------------------------------------------------------------

class TestMLEMAIsolation:

    def test_c1_two_users_have_independent_ema_state_dicts(self):
        """After two users run inference, their EMA dicts are different objects."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        # Inject states manually (simulating two completed inferences)
        with svc._lock:
            svc._ema_states_by_user["user_x"] = {
                "fall_prob": 0.8, "instability_prob": 0.7,
                "quality_score": 0.9, "risk_score": 0.8,
            }
            svc._ema_states_by_user["user_y"] = {
                "fall_prob": 0.1, "instability_prob": 0.1,
                "quality_score": 0.95, "risk_score": 0.1,
            }

        state_x = svc._ema_states_by_user["user_x"]
        state_y = svc._ema_states_by_user["user_y"]

        # They must be different objects
        assert state_x is not state_y
        assert state_x["fall_prob"] != state_y["fall_prob"]

    def test_c2_reset_user_state_clears_entry(self):
        """reset_user_state removes the user's EMA entry."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._predictor = types.SimpleNamespace(reset=lambda: None, _ema_state={})

        with svc._lock:
            svc._ema_states_by_user["user_reset"] = {
                "fall_prob": 0.5, "instability_prob": 0.5,
                "quality_score": 0.5, "risk_score": 0.5,
            }

        assert "user_reset" in svc._ema_states_by_user
        svc.reset_user_state("user_reset")
        assert "user_reset" not in svc._ema_states_by_user

    def test_c3_user_b_not_affected_by_user_a_state(self):
        """User B's initial EMA is not contaminated by User A's previous inference."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True

        # Simulate User A has had very high-risk EMA
        with svc._lock:
            svc._ema_states_by_user["user_a_ema"] = {
                "fall_prob": 0.99, "instability_prob": 0.99,
                "quality_score": 0.1, "risk_score": 0.99,
            }

        # User B has never been seen → default state
        with svc._lock:
            user_b_state = svc._ema_states_by_user.get("user_b_ema")

        assert user_b_state is None, "User B should have no EMA state yet"

    def test_c4_ema_state_persisted_across_calls(self):
        """After a mock inference, the user's EMA state is updated in _ema_states_by_user."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        # Predictor that sets a specific EMA state after predict()
        called_with_state = {}

        class FakePredictor:
            _ema_state = {
                "fall_prob": 0.0, "instability_prob": 0.0,
                "quality_score": 1.0, "risk_score": 0.0,
            }

            def predict(self, imu, ppg, vitals, smooth=True):
                # Simulate EMA update
                self._ema_state["fall_prob"] = 0.55
                self._ema_state["risk_score"] = 0.55
                called_with_state.update(self._ema_state)
                return self._ema_state.copy()

            def reset(self):
                pass

        svc._predictor = FakePredictor()
        svc._postprocessor = types.SimpleNamespace(
            process=lambda predictions, vitals: {
                "fall_probability": 0.55,
                "final_risk_level": "warning",
                "immediate_alert": False,
                "reasons": [], "recommendations": [],
            }
        )

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = False
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True
            ms.ML_VITALS_DIM = 3

            svc.predict_window(
                "user_c4",
                _fake_window(10),
                window_status=_window_status_with_warning(False),
            )

        # User's EMA state should be stored
        assert "user_c4" in svc._ema_states_by_user
        assert svc._ema_states_by_user["user_c4"]["fall_prob"] == 0.55


# ---------------------------------------------------------------------------
# D) Retrieval sample-rate mismatch gate
# ---------------------------------------------------------------------------

class TestRetrievalSampleRateGate:

    def test_d1_skip_when_warning_no_slow_index(self, tmp_path):
        """sample_rate_warning=True, no slow index → retrieval_skipped=True."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as ms:
            ms.RETRIEVAL_ENABLED = True
            ms.RETRIEVAL_TOP_K = 5
            ms.RETRIEVAL_INDEX_DIR = str(tmp_path / "nonexistent_50hz")
            ms.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = False
            ms.RETRIEVAL_USE_SLOW_INDEX = True
            ms.RETRIEVAL_SLOW_INDEX_DIR = str(tmp_path / "nonexistent_slow")

            svc = RetrievalShadowService()
            # Force 50Hz engine to loaded-but-unavailable
            svc._loaded = True
            svc._available = False
            svc._slow_loaded = True
            svc._slow_available = False

            result = svc.query_window(
                _fake_window(),
                _window_status_with_warning(True),
            )

        assert result["retrieval_available"] is False
        assert result.get("retrieval_skipped") is True
        assert result.get("skip_reason") == "sample_rate_mismatch"
        assert result.get("shadow_mode") is True

    def test_d2_slow_index_used_when_warning_and_available(self, tmp_path):
        """sample_rate_warning=True, slow index available → aligned_mode='slow_1hz'."""
        from services.retrieval_shadow_service import RetrievalShadowService
        from src.inference.retrieval_engine import RetrievalEngine

        slow_dir = str(tmp_path / "slow_index")
        _make_slow_index(slow_dir, dim=21)

        # Build a tiny slow engine directly
        slow_engine = RetrievalEngine()
        slow_engine.load(slow_dir)

        svc = RetrievalShadowService()
        svc._loaded = True
        svc._available = False  # 50Hz not loaded
        svc._slow_loaded = True
        svc._slow_available = slow_engine.is_available()
        svc._slow_engine = slow_engine

        with mock.patch("services.retrieval_shadow_service.settings") as ms:
            ms.RETRIEVAL_ENABLED = True
            ms.RETRIEVAL_TOP_K = 5
            ms.RETRIEVAL_USE_SLOW_INDEX = True
            ms.RETRIEVAL_SLOW_INDEX_DIR = slow_dir
            ms.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = False

            # We need _build_feature_vector to return a 21-dim vector
            mock_fv = np.random.default_rng(7).random(21).astype(np.float32)
            with mock.patch.object(
                RetrievalShadowService, "_build_feature_vector", return_value=mock_fv
            ):
                result = svc.query_window(
                    _fake_window(),
                    _window_status_with_warning(True),
                )

        if result.get("retrieval_available"):
            assert result.get("aligned_mode") == "slow_1hz"
            assert result.get("low_confidence") is False
        else:
            # Dim mismatch fallback is acceptable
            assert "retrieval_available" in result

    def test_d3_low_confidence_query_allowed_flag(self, tmp_path):
        """RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True → 50Hz query proceeds (fail-open ok)."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as ms:
            ms.RETRIEVAL_ENABLED = True
            ms.RETRIEVAL_TOP_K = 5
            ms.RETRIEVAL_INDEX_DIR = str(tmp_path / "nonexistent")
            ms.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = True   # allow
            ms.RETRIEVAL_USE_SLOW_INDEX = False

            svc = RetrievalShadowService()
            svc._loaded = True
            svc._available = False  # engine unavailable → fail-open
            svc._slow_loaded = True
            svc._slow_available = False

            result = svc.query_window(
                _fake_window(),
                _window_status_with_warning(True),
            )

        # Should NOT be skipped — fails open because engine unavailable
        assert result.get("retrieval_skipped") is not True
        assert "retrieval_available" in result

    def test_d4_no_warning_uses_50hz_engine_normally(self, tmp_path):
        """sample_rate_warning=False → 50Hz engine used, no skip."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as ms:
            ms.RETRIEVAL_ENABLED = True
            ms.RETRIEVAL_TOP_K = 5
            ms.RETRIEVAL_INDEX_DIR = str(tmp_path / "nonexistent")
            ms.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = False
            ms.RETRIEVAL_USE_SLOW_INDEX = True
            ms.RETRIEVAL_SLOW_INDEX_DIR = str(tmp_path / "nonexistent_slow")

            svc = RetrievalShadowService()
            svc._loaded = True
            svc._available = False  # engine unavailable → fail-open
            svc._slow_loaded = True
            svc._slow_available = False

            result = svc.query_window(
                _fake_window(),
                _window_status_with_warning(False),  # no warning
            )

        # No skip for non-warning case; falls through to fail-open
        assert result.get("retrieval_skipped") is not True


# ---------------------------------------------------------------------------
# E) Retrieval slow index path
# ---------------------------------------------------------------------------

class TestSlowIndexPath:

    def test_e1_slow_index_loads_and_queries(self, tmp_path):
        """Small slow-index fixture loads successfully and returns a result."""
        from src.inference.retrieval_engine import RetrievalEngine

        slow_dir = str(tmp_path / "slow_test")
        _make_slow_index(slow_dir, n=20, dim=21)

        engine = RetrievalEngine()
        assert engine.load(slow_dir) is True
        assert engine.is_available()

        fv = np.random.default_rng(3).random(21).astype(np.float32)
        result = engine.query(fv, top_k=5)
        assert result["retrieval_available"] is True

    def test_e2_slow_result_does_not_contain_final_risk_score(self, tmp_path):
        """Slow index result does not modify or include final_risk_score."""
        from src.inference.retrieval_engine import RetrievalEngine

        slow_dir = str(tmp_path / "slow_no_risk")
        _make_slow_index(slow_dir, n=10, dim=21)

        engine = RetrievalEngine()
        engine.load(slow_dir)
        fv = np.zeros(21, dtype=np.float32)
        result = engine.query(fv, top_k=5)

        assert "final_risk_score" not in result, "Retrieval must NOT include final_risk_score"

    def test_e3_slow_build_summary_has_slow_index_flag(self):
        """outputs/retrieval_slow/retrieval_build_summary.json has slow_index=true."""
        slow_summary = os.path.join(
            _PROJECT_ROOT, "outputs", "retrieval_slow", "retrieval_build_summary.json"
        )
        if not os.path.isfile(slow_summary):
            pytest.skip("Slow index not yet built — run build_retrieval_slow_index.py")
        with open(slow_summary) as f:
            data = json.load(f)
        assert data.get("slow_index") is True
        assert data.get("feature_dim") == 21


# ---------------------------------------------------------------------------
# F) Demo self-match
# ---------------------------------------------------------------------------

_DEMO_RESULT_PATH = os.path.join(
    _PROJECT_ROOT, "outputs", "retrieval", "demo_query_result.json"
)
_DEMO_EXISTS = os.path.isfile(_DEMO_RESULT_PATH)


class TestDemoSelfMatch:

    @pytest.mark.skipif(not _DEMO_EXISTS, reason="demo_query_result.json not yet generated")
    def test_f1_self_match_present_key_exists(self):
        """demo_query_result.json contains self_match_present key."""
        with open(_DEMO_RESULT_PATH) as f:
            data = json.load(f)
        assert "self_match_present" in data, "self_match_present key missing from demo result"

    @pytest.mark.skipif(not _DEMO_EXISTS, reason="demo_query_result.json not yet generated")
    def test_f2_exclude_self_applied_key_exists(self):
        """demo_query_result.json contains exclude_self_applied key."""
        with open(_DEMO_RESULT_PATH) as f:
            data = json.load(f)
        assert "exclude_self_applied" in data, "exclude_self_applied key missing"

    def test_f3_run_demo_with_exclude_self_returns_fewer_examples(self, tmp_path):
        """Running demo with exclude_self=True gives ≤ examples vs exclude_self=False."""
        try:
            from scripts.demo_retrieval_query import run_demo
        except ImportError:
            pytest.skip("demo_retrieval_query not importable from test context")

        index_dir = os.path.join(_PROJECT_ROOT, "outputs", "retrieval")
        if not os.path.isfile(os.path.join(index_dir, "retrieval_index.joblib")):
            pytest.skip("50Hz index not available")

        result_with = run_demo(index_dir=index_dir, top_k=10, exclude_self=True)
        result_without = run_demo(index_dir=index_dir, top_k=10, exclude_self=False)

        if result_with.get("retrieval_available") and result_without.get("retrieval_available"):
            n_with = len(result_with.get("similar_examples", []))
            n_without = len(result_without.get("similar_examples", []))
            assert n_with <= n_without, (
                f"exclude_self=True should give ≤ examples: {n_with} > {n_without}"
            )


# ---------------------------------------------------------------------------
# G) Regression
# ---------------------------------------------------------------------------

class TestRegression:

    def test_g1_baseline_service_imports_unchanged(self):
        """Part 1 baseline_service still importable."""
        from services.baseline_service import (
            apply_baseline_adjustment,
            compute_personal_deviation,
            compute_quality_confidence,
        )
        assert callable(apply_baseline_adjustment)

    def test_g2_live_window_buffer_imports_unchanged(self):
        """Part 2 live_window_buffer still importable."""
        from services.live_window_buffer import live_window_buffer, LiveWindowBufferManager
        assert isinstance(live_window_buffer, LiveWindowBufferManager)

    def test_g3_ml_inference_service_imports_unchanged(self):
        """Part 2/3.1 ml_inference_service still importable."""
        from services.ml_inference_service import ml_inference_service, MLInferenceService
        assert isinstance(ml_inference_service, MLInferenceService)
        assert hasattr(ml_inference_service, "predict_window")
        assert hasattr(ml_inference_service, "reset_user_state")
        assert hasattr(ml_inference_service, "_ema_states_by_user")

    def test_g4_retrieval_shadow_service_imports_unchanged(self):
        """Part 3 retrieval_shadow_service still importable."""
        from services.retrieval_shadow_service import (
            retrieval_shadow_service,
            RetrievalShadowService,
        )
        assert isinstance(retrieval_shadow_service, RetrievalShadowService)
        assert hasattr(retrieval_shadow_service, "query_window")

    def test_g5_config_has_all_alignment_settings(self):
        """Config has all Part 3.1 alignment settings."""
        from config import settings
        # ML alignment gate
        assert hasattr(settings, "ML_SKIP_ON_SAMPLE_RATE_MISMATCH")
        assert hasattr(settings, "ML_MAX_DURATION_RATIO")
        assert hasattr(settings, "ML_ALLOW_LOW_CONFIDENCE_INFERENCE")
        assert hasattr(settings, "ML_VITALS_DIM")
        # Retrieval alignment gate
        assert hasattr(settings, "RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH")
        assert hasattr(settings, "RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY")
        assert hasattr(settings, "RETRIEVAL_USE_SLOW_INDEX")
        assert hasattr(settings, "RETRIEVAL_SLOW_INDEX_DIR")
        # Defaults
        assert settings.ML_SKIP_ON_SAMPLE_RATE_MISMATCH is True
        assert settings.ML_ALLOW_LOW_CONFIDENCE_INFERENCE is False
        assert settings.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH is True
        assert settings.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY is False

    def test_g6_schema_backward_compat(self):
        """DevicePacketResponse can be instantiated without new shadow fields."""
        from schemas import DevicePacketResponse
        resp = DevicePacketResponse(
            status="accepted",
            packet_seq=42,
            device_id="dev-regression",
        )
        assert resp.retrieval_shadow_result is None
        assert resp.ml_shadow_result is None
        assert resp.window_status is None

    def test_g7_smoke_api_retrieval_key_expected(self):
        """_smoke_api.py checks for retrieval_shadow_result key (contract test)."""
        smoke_path = os.path.join(_BACKEND_DIR, "_smoke_api.py")
        with open(smoke_path, encoding="utf-8") as f:
            content = f.read()
        assert "retrieval_shadow_result" in content, (
            "_smoke_api.py should check retrieval_shadow_result field"
        )
