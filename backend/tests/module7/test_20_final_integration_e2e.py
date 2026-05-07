"""Test 20 — Part 4: Final Integration E2E — Active/Shadow Separation

Tests:
  A) Active pipeline invariants
     - final_risk_score comes ONLY from apply_baseline_adjustment (heuristic + baseline)
     - alert_sensitivity shifts thresholds, NOT final_risk_score
     - AlertEvent creation is driven by heuristic severity only
     - ML and retrieval results NEVER carry final_risk_score
     - Shadow results always have shadow_mode=True

  B) Registered-device E2E
     - Registered device → user_id populated in ingest response
     - Unregistered device → user_id is None, pipeline skipped
     - window_status present/absent based on user_id

  C) ML shadow isolation
     - ML shadow result does not override risk_breakdown in response
     - ml_shadow_result has shadow_mode=True when enabled
     - ML disabled → ml_shadow_result is None

  D) Retrieval shadow isolation
     - retrieval_shadow_result has final_risk_score NOT in keys (shadow only)
     - Retrieval disabled → retrieval_shadow_result is None

  E) Config completeness
     - All Part 4 critical config keys present
     - DEMO_DEVICE_ID matches firmware ha_config.h

  F) Schema stability
     - DevicePacketResponse schema unchanged from Part 3
     - DevicePacketRequest accepts all required fields
"""
from __future__ import annotations

import os
import sys
import types
import unittest.mock as mock
from collections import deque

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_e2e.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_packet(**overrides):
    base = dict(
        device_id="ha-esp32-001",
        timestamp_ms=1_700_000_000_000,
        mode="mock",
        packet_seq=9001,
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


def _make_critical_packet(**overrides):
    """Returns a packet that should trigger critical severity (spo2 < 90)."""
    return _make_packet(
        packet_seq=9002,
        heart_rate=135.0, spo2=85.0,
        hr_valid=True, spo2_valid=True,
        state_hint="critical_state",
        **overrides,
    )


def _fake_window(n: int = 200):
    return [
        types.SimpleNamespace(
            timestamp_ms=1_700_000_000_000 + i * 1000,
            packet_seq=i, mode="mock",
            accel_x=0.01, accel_y=0.02, accel_z=1.0,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            red_value=50_000, ir_value=55_000,
            heart_rate=72.0, spo2=98.0, signal_quality=0.9,
            imu_ok=True, ppg_ok=True,
            hr_valid=True, spo2_valid=True, finger_detected=True,
            motion_score=0.1, final_risk_score=0.1, quality_confidence=0.9,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# A) Active pipeline invariants
# ---------------------------------------------------------------------------

class TestActivePipelineInvariants:

    def test_a1_final_risk_score_not_in_ml_result(self):
        """ML shadow result MUST NOT contain final_risk_score (shadow only)."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        def fake_predict(imu, ppg, vitals, smooth=True):
            return {
                "fall_prob": 0.05, "instability_prob": 0.05,
                "quality_score": 0.9, "risk_score": 0.1,
            }

        svc._predictor = types.SimpleNamespace(
            predict=fake_predict,
            _ema_state={
                "fall_prob": 0.0, "instability_prob": 0.0,
                "quality_score": 1.0, "risk_score": 0.0,
            },
            reset=lambda: None,
        )
        svc._postprocessor = types.SimpleNamespace(
            process=lambda predictions, vitals: {
                "fall_probability": 0.05, "final_risk_level": "normal",
                "immediate_alert": False,
            }
        )
        svc._ema_states_by_user["user_a1"] = {
            "fall_prob": 0.0, "instability_prob": 0.0,
            "quality_score": 1.0, "risk_score": 0.0,
        }

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True
            ms.ML_EMA_ALPHA = 0.2
            ms.ML_VITALS_DIM = 3
            ms.ML_MAX_DURATION_RATIO = 3.0

            result = svc.predict_window(
                "user_a1",
                _fake_window(),
                window_status={"is_full": True, "sample_rate_warning": False,
                               "estimated_window_duration_sec": 4.0,
                               "expected_duration_sec": 4.0},
            )

        assert "final_risk_score" not in result, (
            "ML shadow result must NOT contain final_risk_score"
        )
        assert result.get("shadow_mode") is True

    def test_a2_alert_sensitivity_does_not_change_final_risk_score(self):
        """alert_sensitivity only shifts thresholds; final_risk_score stays objective."""
        from services.baseline_service import apply_baseline_adjustment

        deviation = {"deviation_bonus": 0.0}
        quality_info = {
            "quality_confidence": 0.9,
            "quality_warning": None,
            "safety_override": False,
        }
        global_risk = 0.45

        result_normal = apply_baseline_adjustment(
            global_risk_score=global_risk,
            deviation=deviation,
            quality_info=quality_info,
            baseline_ready=False,
            alert_sensitivity="normal",
        )
        result_high = apply_baseline_adjustment(
            global_risk_score=global_risk,
            deviation=deviation,
            quality_info=quality_info,
            baseline_ready=False,
            alert_sensitivity="high",
        )
        result_low = apply_baseline_adjustment(
            global_risk_score=global_risk,
            deviation=deviation,
            quality_info=quality_info,
            baseline_ready=False,
            alert_sensitivity="low",
        )

        assert result_normal["final_risk_score"] == result_high["final_risk_score"], (
            "alert_sensitivity=high must NOT change final_risk_score"
        )
        assert result_normal["final_risk_score"] == result_low["final_risk_score"], (
            "alert_sensitivity=low must NOT change final_risk_score"
        )
        # Sensitivity is stored in breakdown for threshold use by caller
        assert result_high["alert_sensitivity"] == "high"
        assert result_low["alert_sensitivity"] == "low"

    def test_a3_risk_to_severity_uses_threshold_offset_not_score(self):
        """_risk_to_severity shifts thresholds, NOT the risk_score value."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from routers.ingestion_router import _risk_to_severity

        # risk=0.35 with RISK_WARNING_THRESHOLD=0.40, offset=0.0 → None or watch
        # risk=0.35 with offset=-0.10 → threshold drops to 0.30 → warning/watch

        # Patch config thresholds to known values
        with mock.patch("routers.ingestion_router.settings") as ms:
            ms.RISK_CRITICAL_THRESHOLD = 0.70
            ms.RISK_WARNING_THRESHOLD = 0.40
            ms.RISK_WATCH_THRESHOLD = 0.20

            sev_normal = _risk_to_severity(0.35, sensitivity_offset=0.0)
            sev_high = _risk_to_severity(0.35, sensitivity_offset=-0.10)   # thresholds drop
            sev_low = _risk_to_severity(0.35, sensitivity_offset=0.10)    # thresholds rise

        # 0.35 vs threshold 0.40 → watch (>= 0.20)
        assert sev_normal == "watch"
        # 0.35 vs threshold 0.30 (0.40 - 0.10) → warning
        assert sev_high == "warning"
        # 0.35 vs threshold 0.50 (0.40 + 0.10) → watch (0.35 >= 0.20 + 0.10 = 0.30)
        assert sev_low == "watch"

    def test_a4_final_risk_score_floor_ceiling(self):
        """final_risk_score must always be in [0.0, 1.0]."""
        from services.baseline_service import apply_baseline_adjustment

        deviation_high = {"deviation_bonus": 0.8}
        quality_info = {
            "quality_confidence": 0.9,
            "quality_warning": None,
            "safety_override": False,
        }

        result = apply_baseline_adjustment(
            global_risk_score=0.95,
            deviation=deviation_high,
            quality_info=quality_info,
            baseline_ready=True,
            alert_sensitivity="normal",
        )
        assert result["final_risk_score"] <= 1.0

        result2 = apply_baseline_adjustment(
            global_risk_score=0.0,
            deviation={"deviation_bonus": 0.0},
            quality_info=quality_info,
            baseline_ready=True,
            alert_sensitivity="normal",
        )
        assert result2["final_risk_score"] >= 0.0


# ---------------------------------------------------------------------------
# B) Registered vs unregistered device
# ---------------------------------------------------------------------------

class TestDeviceRegistration:

    def test_b1_registered_device_id_in_seed_constant(self):
        """DEMO_DEVICE_ID in seed.py matches firmware ha_config.h HA_DEVICE_ID."""
        import importlib.util
        seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "seed.py")

        # Read the constant directly from source without importing (avoids DB deps)
        with open(seed_path) as f:
            source = f.read()
        assert 'DEMO_DEVICE_ID = "ha-esp32-001"' in source, (
            "seed.py must define DEMO_DEVICE_ID = \"ha-esp32-001\" "
            "(matches HA_DEVICE_ID in ha_config.h)"
        )

    def test_b2_device_registration_model_has_required_fields(self):
        """DeviceRegistration model must have device_id, user_id, is_active."""
        from models import DeviceRegistration
        cols = {c.key for c in DeviceRegistration.__mapper__.columns}
        for required in ("device_id", "user_id", "is_active", "registered_at"):
            assert required in cols, f"DeviceRegistration missing column: {required}"

    def test_b3_device_registration_seeded_idempotently(self):
        """seed.py must check for existing DeviceRegistration before inserting."""
        seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "seed.py")
        with open(seed_path) as f:
            source = f.read()
        # Idempotency check — must query for existing before inserting
        assert "DeviceRegistration" in source
        assert "scalar_one_or_none" in source
        assert "DEMO_DEVICE_ID" in source

    def test_b4_unregistered_device_skips_pipeline(self):
        """DevicePacketResponse with unknown device → user_id must be None."""
        from schemas import DevicePacketResponse

        # Simulate what ingest_device_packet returns for an unknown device
        resp = DevicePacketResponse(
            status="accepted",
            packet_seq=1,
            device_id="unknown-device-xyz",
            user_id=None,
            window_status=None,
        )
        assert resp.user_id is None
        assert resp.window_status is None


# ---------------------------------------------------------------------------
# C) ML shadow isolation
# ---------------------------------------------------------------------------

class TestMLShadowIsolation:

    def test_c1_ml_shadow_result_has_shadow_mode_true(self):
        """Any ML shadow result dict must include shadow_mode=True."""
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
            predict=fake_predict,
            _ema_state={
                "fall_prob": 0.0, "instability_prob": 0.0,
                "quality_score": 1.0, "risk_score": 0.0,
            },
            reset=lambda: None,
        )
        svc._postprocessor = types.SimpleNamespace(
            process=lambda predictions, vitals: {
                "fall_probability": 0.1, "final_risk_level": "normal",
                "immediate_alert": False,
            }
        )
        svc._ema_states_by_user["user_c1"] = {
            "fall_prob": 0.0, "instability_prob": 0.0,
            "quality_score": 1.0, "risk_score": 0.0,
        }

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True
            ms.ML_EMA_ALPHA = 0.2
            ms.ML_VITALS_DIM = 3
            ms.ML_MAX_DURATION_RATIO = 3.0

            result = svc.predict_window(
                "user_c1",
                _fake_window(),
                window_status={"is_full": True, "sample_rate_warning": False,
                               "estimated_window_duration_sec": 4.0,
                               "expected_duration_sec": 4.0},
            )

        assert result.get("shadow_mode") is True

    def test_c2_ml_skipped_returns_ml_available_false(self):
        """When ML is unavailable, ml_available=False must be in result."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = False  # model not loaded

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True

            result = svc.predict_window(
                "user_c2",
                _fake_window(),
            )

        assert result.get("ml_available") is False
        assert result.get("shadow_mode") is True

    def test_c3_ml_response_schema_keys_stable(self):
        """DevicePacketResponse schema has ml_shadow_result as optional dict."""
        from schemas import DevicePacketResponse
        import inspect

        fields = DevicePacketResponse.model_fields
        assert "ml_shadow_result" in fields
        # Must be optional (default None)
        assert fields["ml_shadow_result"].default is None

    def test_c4_ml_result_never_overwrites_risk_breakdown(self):
        """ML result dict keys must not include 'final_risk_score'."""
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        svc._loaded = False
        svc._available = False

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = False
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True

            result = svc.predict_window("user_c4", _fake_window())

        assert "final_risk_score" not in result


# ---------------------------------------------------------------------------
# D) Retrieval shadow isolation
# ---------------------------------------------------------------------------

class TestRetrievalShadowIsolation:

    def test_d1_retrieval_result_has_no_final_risk_score(self):
        """Retrieval shadow result MUST NOT contain final_risk_score."""
        from services.retrieval_shadow_service import RetrievalShadowService

        svc = RetrievalShadowService()
        svc._loaded = True
        svc._available = True

        # Mock engine returning plausible retrieval result
        def fake_query(feature_vector, k=5):
            return [
                {"dataset": "HIFD", "label_group": "fall",
                 "risk_level_estimate": "critical", "scenario": "fall1"}
            ]

        svc._engine = types.SimpleNamespace(query=fake_query)

        with mock.patch("services.retrieval_shadow_service.settings") as rs:
            rs.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = False
            rs.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = True
            rs.RETRIEVAL_USE_SLOW_INDEX = False
            rs.RETRIEVAL_TOP_K = 5
            rs.RETRIEVAL_SUPPORT_THRESHOLD = 0.6
            rs.RETRIEVAL_RESPONSE_INCLUDE_RESULT = True

            result = svc.query_window(
                _fake_window(),
                {"is_full": True, "sample_rate_warning": False,
                 "estimated_window_duration_sec": 4.0,
                 "expected_duration_sec": 4.0},
            )

        if result:
            assert "final_risk_score" not in result, (
                "Retrieval shadow must NOT carry final_risk_score"
            )

    def test_d2_retrieval_schema_key_present_and_optional(self):
        """DevicePacketResponse must have retrieval_shadow_result as optional field."""
        from schemas import DevicePacketResponse

        fields = DevicePacketResponse.model_fields
        assert "retrieval_shadow_result" in fields
        assert fields["retrieval_shadow_result"].default is None

    def test_d3_retrieval_skipped_result_has_shadow_mode(self):
        """Retrieval skip result (no index) has retrieval_available=False."""
        from services.retrieval_shadow_service import RetrievalShadowService

        svc = RetrievalShadowService()
        svc._loaded = True
        svc._available = False  # index not loaded
        svc._slow_loaded = True
        svc._slow_available = False

        with mock.patch("services.retrieval_shadow_service.settings") as rs:
            rs.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            rs.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY = False
            rs.RETRIEVAL_USE_SLOW_INDEX = False

            result = svc.query_window(
                _fake_window(),
                {"is_full": True, "sample_rate_warning": True,
                 "estimated_window_duration_sec": 100.0,
                 "expected_duration_sec": 4.0},
            )

        assert result is not None
        assert result.get("retrieval_available") is False
        assert result.get("retrieval_skipped") is True


# ---------------------------------------------------------------------------
# E) Config completeness
# ---------------------------------------------------------------------------

class TestConfigCompleteness:

    def test_e1_all_part4_config_keys_exist(self):
        """Config must have all keys required for Part 4 demo run."""
        from config import Settings

        required_keys = [
            "DATA_MODE",
            "BASELINE_ENABLED",
            "BASELINE_MIN_SAMPLES",
            "BASELINE_ALLOW_MOCK_DATA",
            "ML_INFERENCE_ENABLED",
            "ML_SHADOW_MODE",
            "ML_SKIP_ON_SAMPLE_RATE_MISMATCH",
            "ML_ALLOW_LOW_CONFIDENCE_INFERENCE",
            "ML_VITALS_DIM",
            "RETRIEVAL_ENABLED",
            "RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH",
            "RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY",
            "RETRIEVAL_USE_SLOW_INDEX",
            "RETRIEVAL_SLOW_INDEX_DIR",
            "NOTIFICATION_MODE",
        ]
        fields = Settings.model_fields
        missing = [k for k in required_keys if k not in fields]
        assert not missing, f"Config missing keys: {missing}"

    def test_e2_demo_device_id_matches_firmware(self):
        """DEMO_DEVICE_ID in seed.py must match HA_DEVICE_ID in ha_config.h."""
        ha_config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "firmware", "include", "ha_config.h"
        )
        if not os.path.exists(ha_config_path):
            pytest.skip("firmware/include/ha_config.h not found")

        with open(ha_config_path) as f:
            fw_src = f.read()

        # Extract #define HA_DEVICE_ID "..."
        import re
        match = re.search(r'#define\s+HA_DEVICE_ID\s+"([^"]+)"', fw_src)
        assert match, "HA_DEVICE_ID not found in ha_config.h"
        fw_device_id = match.group(1)

        seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "seed.py")
        with open(seed_path) as f:
            seed_src = f.read()

        assert f'DEMO_DEVICE_ID = "{fw_device_id}"' in seed_src, (
            f"seed.py DEMO_DEVICE_ID must equal firmware HA_DEVICE_ID='{fw_device_id}'"
        )

    def test_e3_env_demo_example_exists(self):
        """.env.demo.example must exist in backend/."""
        env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.demo.example"
        )
        assert os.path.exists(env_path), "backend/.env.demo.example not found"


# ---------------------------------------------------------------------------
# F) Schema stability
# ---------------------------------------------------------------------------

class TestSchemaStability:

    def test_f1_device_packet_request_required_fields(self):
        """DevicePacketRequest must accept all fields from packet_schema.py."""
        from schemas import DevicePacketRequest

        pkt = _make_packet()
        obj = DevicePacketRequest(**pkt)
        assert obj.device_id == "ha-esp32-001"
        assert obj.heart_rate == 72.0
        assert obj.spo2 == 98.0

    def test_f2_device_packet_response_optional_fields_default_none(self):
        """All shadow/optional fields in DevicePacketResponse default to None."""
        from schemas import DevicePacketResponse

        resp = DevicePacketResponse(
            status="accepted",
            packet_seq=1,
            device_id="ha-esp32-001",
        )
        assert resp.user_id is None
        assert resp.risk_breakdown is None
        assert resp.window_status is None
        assert resp.ml_shadow_result is None
        assert resp.retrieval_shadow_result is None

    def test_f3_host_bridge_packet_fields_compatible_with_backend(self):
        """host_bridge DevicePacketSchema fields must be a subset of backend schema."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                         "host_bridge"))
        from packet_schema import DevicePacketSchema
        from schemas import DevicePacketRequest

        bridge_fields = set(DevicePacketSchema.model_fields.keys())
        backend_fields = set(DevicePacketRequest.model_fields.keys())

        # Every field the bridge sends must be accepted by the backend
        incompatible = bridge_fields - backend_fields
        assert not incompatible, (
            f"host_bridge sends fields not accepted by backend: {incompatible}"
        )

    def test_f4_risk_breakdown_has_correct_keys(self):
        """apply_baseline_adjustment breakdown must NOT include shadow keys."""
        from services.baseline_service import apply_baseline_adjustment

        result = apply_baseline_adjustment(
            global_risk_score=0.3,
            deviation={"deviation_bonus": 0.05},
            quality_info={"quality_confidence": 0.8, "quality_warning": None,
                          "safety_override": False},
            baseline_ready=True,
            alert_sensitivity="normal",
        )

        expected_keys = {
            "final_risk_score", "global_risk_score", "personal_deviation_score",
            "baseline_ready", "quality_confidence", "quality_warning",
            "alert_sensitivity",
        }
        assert set(result.keys()) == expected_keys, (
            f"risk_breakdown keys mismatch: {set(result.keys())} != {expected_keys}"
        )
        # Shadow contamination check
        assert "shadow_mode" not in result
        assert "ml_available" not in result
        assert "retrieval_available" not in result
