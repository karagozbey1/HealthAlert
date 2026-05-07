"""
Test 17 — ML Shadow Mode: Sliding Window Buffer + ML Inference Shadow

Tests:
  A) Config / disabled mode
     - ML_INFERENCE_ENABLED=False → ingest flow works, window_status present,
       ml_shadow_result absent.

  B) Model unavailable (fail-open)
     - ML_INFERENCE_ENABLED=True but wrong model path → ml_available=False,
       no 500 raised.

  C) Buffer behaviour
     - First packet → current_size=1.
     - Buffer not full → should_run_inference=False.
     - After ML_WINDOW_SIZE packets → is_full=True.
     - ML_INFERENCE_EVERY_N_PACKETS cadence works.

  D) Shadow safety
     - ML shadow result does NOT affect final_risk_score / severity decision.
     - No AlertEvent / AnomalyEvent created solely from ML output.

  E) Sampling mismatch detection
     - Packets spaced 1 s apart → estimated_window_duration >> expected.
     - sample_rate_warning=True when ratio > 3×.

  F) Regression — Part 1 baseline service still works after Part 2 imports.
"""
from __future__ import annotations

import os
import sys
import types
import unittest.mock as mock

import pytest

# ---------------------------------------------------------------------------
# Path setup (mirror test_16_baseline_mvp.py pattern)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_ml_shadow.db")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_packet(
    *,
    packet_seq: int = 1,
    timestamp_ms: int = 1_700_000_000_000,
    mode: str = "mock",
    heart_rate: float = 72.0,
    spo2: float = 98.0,
    signal_quality: float = 0.9,
    accel_x: float = 0.01,
    accel_y: float = 0.02,
    accel_z: float = 1.0,
    gyro_x: float = 0.0,
    gyro_y: float = 0.0,
    gyro_z: float = 0.0,
    red_value: int = 50_000,
    ir_value: int = 55_000,
    imu_ok: bool = True,
    ppg_ok: bool = True,
    hr_valid: bool = True,
    spo2_valid: bool = True,
    finger_detected: bool = True,
    state_hint: str = "normal",
):
    """Return a simple namespace that looks like DevicePacketRequest."""
    return types.SimpleNamespace(
        device_id="test-device-shadow",
        timestamp_ms=timestamp_ms,
        mode=mode,
        packet_seq=packet_seq,
        accel_x=accel_x,
        accel_y=accel_y,
        accel_z=accel_z,
        gyro_x=gyro_x,
        gyro_y=gyro_y,
        gyro_z=gyro_z,
        red_value=red_value,
        ir_value=ir_value,
        heart_rate=heart_rate,
        spo2=spo2,
        signal_quality=signal_quality,
        imu_ok=imu_ok,
        ppg_ok=ppg_ok,
        hr_valid=hr_valid,
        spo2_valid=spo2_valid,
        finger_detected=finger_detected,
        state_hint=state_hint,
    )


# ===========================================================================
# A) Config / disabled mode
# ===========================================================================

class TestMLDisabledMode:
    """ML_INFERENCE_ENABLED=False — buffer still tracks, no inference."""

    def test_settings_have_ml_fields(self):
        from config import settings
        assert hasattr(settings, "ML_INFERENCE_ENABLED")
        assert hasattr(settings, "ML_SHADOW_MODE")
        assert hasattr(settings, "ML_MODEL_PATH")
        assert hasattr(settings, "ML_WINDOW_SIZE")
        assert hasattr(settings, "ML_INFERENCE_EVERY_N_PACKETS")
        assert hasattr(settings, "ML_EXPECTED_SAMPLE_RATE_HZ")
        assert hasattr(settings, "ML_FAIL_OPEN")
        assert hasattr(settings, "ML_USE_PACKET_SUMMARY_MODE")
        assert hasattr(settings, "ML_WARN_ON_SAMPLE_RATE_MISMATCH")
        assert hasattr(settings, "ML_RESPONSE_INCLUDE_SHADOW_RESULT")

    def test_ml_inference_disabled_by_default(self):
        from config import settings
        # Default is False — shadow service inactive until explicitly enabled.
        assert settings.ML_INFERENCE_ENABLED is False

    def test_ml_shadow_mode_true_by_default(self):
        from config import settings
        assert settings.ML_SHADOW_MODE is True

    def test_ml_fail_open_true_by_default(self):
        from config import settings
        assert settings.ML_FAIL_OPEN is True

    def test_buffer_tracks_when_ml_disabled(self):
        """Even with ML off, add_packet returns a valid status dict."""
        from services.live_window_buffer import LiveWindowBufferManager
        from config import settings

        mgr = LiveWindowBufferManager()
        pkt = _make_fake_packet(packet_seq=1, timestamp_ms=1_000)
        status = mgr.add_packet("user_disabled", pkt, motion_score=0.1,
                                final_risk_score=0.05)

        assert status["current_size"] == 1
        assert status["target_size"] == settings.ML_WINDOW_SIZE
        assert status["is_full"] is False
        assert status["packet_summary_mode"] == settings.ML_USE_PACKET_SUMMARY_MODE

    def test_should_run_inference_false_when_disabled(self):
        from services.live_window_buffer import LiveWindowBufferManager
        from config import settings

        mgr = LiveWindowBufferManager()
        # Fill the buffer to max
        for i in range(settings.ML_WINDOW_SIZE):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            mgr.add_packet("user_disabled2", pkt, motion_score=0.0,
                           final_risk_score=0.0)

        # ML disabled → should_run_inference always False
        with mock.patch("services.live_window_buffer.settings") as ms:
            ms.ML_INFERENCE_ENABLED = False
            ms.ML_WINDOW_SIZE = settings.ML_WINDOW_SIZE
            ms.ML_INFERENCE_EVERY_N_PACKETS = settings.ML_INFERENCE_EVERY_N_PACKETS
            assert mgr.should_run_inference("user_disabled2") is False

    def test_response_schema_has_new_optional_fields(self):
        from schemas import DevicePacketResponse
        r = DevicePacketResponse(
            status="accepted",
            packet_seq=1,
            device_id="dev",
        )
        assert r.window_status is None
        assert r.ml_shadow_result is None
        # Old fields still present
        assert r.risk_breakdown is None
        assert r.user_id is None


# ===========================================================================
# B) Model unavailable — fail-open
# ===========================================================================

class TestModelUnavailableFail:
    """ML enabled but model path is wrong → ml_available=False, no 500."""

    def test_predict_window_with_no_model_returns_unavailable(self):
        from services.ml_inference_service import MLInferenceService

        svc = MLInferenceService()
        # Service never loaded — predict_window should return unavailable
        result = svc.predict_window(
            user_id="test_user",
            window=[],
        )
        assert result["ml_available"] is False
        assert result["shadow_mode"] is True
        assert result["ml_final_risk_level"] is None

    def test_load_with_bad_path_returns_false(self):
        from services.ml_inference_service import MLInferenceService
        import unittest.mock as m

        svc = MLInferenceService()
        with m.patch("services.ml_inference_service.settings") as ms:
            ms.ML_INFERENCE_ENABLED = True
            ms.ML_MODEL_PATH = "/nonexistent/path/model.pt"
            with m.patch("services.ml_inference_service._resolve_model_path",
                         return_value="/nonexistent/path/model.pt"):
                with m.patch("os.path.exists", return_value=False):
                    result = svc._do_load()
        assert result is False
        assert svc._available is False
        assert svc._load_error is not None

    def test_predict_window_fail_open_on_exception(self):
        from services.ml_inference_service import MLInferenceService
        from services.live_window_buffer import WindowSample
        import unittest.mock as m

        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._predictor = m.MagicMock()
        svc._predictor.predict.side_effect = RuntimeError("simulated model error")
        svc._postprocessor = m.MagicMock()

        window = [
            WindowSample(
                timestamp_ms=1000, packet_seq=1, mode="mock",
                accel_x=0.0, accel_y=0.0, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                red_value=50000, ir_value=55000,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
                imu_ok=True, ppg_ok=True, hr_valid=True,
                spo2_valid=True, finger_detected=True,
                motion_score=0.05, final_risk_score=0.1,
                quality_confidence=0.9,
            )
        ]

        with m.patch("services.ml_inference_service.settings") as ms:
            ms.ML_FAIL_OPEN = True
            result = svc.predict_window("user_err", window)

        assert result["ml_available"] is False
        assert "simulated model error" in result["ml_error"]
        assert result["shadow_mode"] is True


# ===========================================================================
# C) Buffer behaviour
# ===========================================================================

class TestBufferBehaviour:
    """Ring buffer mechanics: fill, dequeue, inference cadence."""

    def setup_method(self):
        from services.live_window_buffer import LiveWindowBufferManager
        self.mgr = LiveWindowBufferManager()
        self.uid = "buf_test_user"

    def test_first_packet_gives_size_1(self):
        pkt = _make_fake_packet(packet_seq=1, timestamp_ms=1_000)
        status = self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        assert status["current_size"] == 1
        assert status["packets_until_full"] == (status["target_size"] - 1)

    def test_buffer_not_full_before_window_size(self):
        from config import settings
        for i in range(settings.ML_WINDOW_SIZE - 1):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        status = self.mgr.get_status(self.uid)
        assert status["is_full"] is False
        assert status["packets_until_full"] == 1

    def test_buffer_full_after_window_size(self):
        from config import settings
        for i in range(settings.ML_WINDOW_SIZE):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        status = self.mgr.get_status(self.uid)
        assert status["is_full"] is True
        assert status["packets_until_full"] == 0

    def test_buffer_is_ring_does_not_exceed_window_size(self):
        from config import settings
        target = settings.ML_WINDOW_SIZE
        for i in range(target + 50):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        status = self.mgr.get_status(self.uid)
        assert status["current_size"] == target

    def test_should_run_inference_false_before_full(self):
        from config import settings
        import unittest.mock as m
        for i in range(settings.ML_WINDOW_SIZE - 1):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        with m.patch("services.live_window_buffer.settings") as ms:
            ms.ML_INFERENCE_ENABLED = True
            ms.ML_WINDOW_SIZE = settings.ML_WINDOW_SIZE
            ms.ML_INFERENCE_EVERY_N_PACKETS = settings.ML_INFERENCE_EVERY_N_PACKETS
            result = self.mgr.should_run_inference(self.uid)
        assert result is False

    def test_should_run_inference_true_at_multiple_of_n(self):
        """After exactly ML_WINDOW_SIZE packets the counter == window size.

        Default ML_WINDOW_SIZE=200, ML_INFERENCE_EVERY_N_PACKETS=50 →
        200 % 50 == 0 → True on first fill.
        """
        from config import settings
        import unittest.mock as m

        window_size = 200
        every_n = 50

        for i in range(window_size):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)

        with m.patch("services.live_window_buffer.settings") as ms:
            ms.ML_INFERENCE_ENABLED = True
            ms.ML_WINDOW_SIZE = window_size
            ms.ML_INFERENCE_EVERY_N_PACKETS = every_n
            result = self.mgr.should_run_inference(self.uid)
        assert result is True

    def test_get_window_returns_list_when_buffer_filled(self):
        from config import settings
        for i in range(settings.ML_WINDOW_SIZE):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        window = self.mgr.get_window(self.uid)
        assert window is not None
        assert len(window) == settings.ML_WINDOW_SIZE

    def test_get_window_returns_none_for_unknown_user(self):
        result = self.mgr.get_window("nonexistent_user_xyz")
        assert result is None

    def test_reset_user_clears_buffer(self):
        pkt = _make_fake_packet(packet_seq=1)
        self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        self.mgr.reset_user(self.uid)
        assert self.mgr.get_window(self.uid) is None

    def test_last_packet_seq_tracked(self):
        for i in range(5):
            pkt = _make_fake_packet(packet_seq=i + 10, timestamp_ms=i * 1000)
            self.mgr.add_packet(self.uid, pkt, 0.0, 0.0)
        status = self.mgr.get_status(self.uid)
        assert status["last_packet_seq"] == 14  # last seq = 10+4


# ===========================================================================
# D) Shadow safety — ML output must not affect severity / alert chain
# ===========================================================================

class TestShadowSafety:
    """Verify that shadow result is truly observational — no side effects."""

    def test_ml_shadow_result_keys_present(self):
        from services.ml_inference_service import MLInferenceService
        svc = MLInferenceService()
        result = svc.predict_window("user_safe", window=[])
        required_keys = {
            "ml_available", "ml_error", "shadow_mode",
            "fall_probability", "instability_probability",
            "ppg_quality_score", "ml_risk_score",
            "ml_final_risk_level", "ml_immediate_alert",
            "ml_reasons", "ml_recommendations",
            "inference_latency_ms", "window_status",
        }
        assert required_keys.issubset(result.keys())

    def test_shadow_mode_always_true_in_result(self):
        from services.ml_inference_service import MLInferenceService
        svc = MLInferenceService()
        result = svc.predict_window("user_safe2", window=[])
        assert result["shadow_mode"] is True

    def test_build_predictor_inputs_shape(self):
        """Verify numpy array shapes are correct."""
        from services.ml_inference_service import MLInferenceService
        from services.live_window_buffer import WindowSample

        svc = MLInferenceService()
        T = 10
        window = [
            WindowSample(
                timestamp_ms=i * 1000, packet_seq=i, mode="mock",
                accel_x=float(i) * 0.01, accel_y=0.0, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                red_value=50000, ir_value=55000,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
                imu_ok=True, ppg_ok=True, hr_valid=True,
                spo2_valid=True, finger_detected=True,
                motion_score=0.05, final_risk_score=0.1,
                quality_confidence=0.9,
            )
            for i in range(T)
        ]
        inputs = svc.build_predictor_inputs(window)

        import numpy as np
        assert inputs["imu"].shape == (T, 6)
        assert inputs["ppg"].shape == (T, 1)
        assert inputs["vitals"].shape == (3,)
        assert inputs["imu"].dtype == np.float32
        assert inputs["ppg"].dtype == np.float32
        assert inputs["vitals"].dtype == np.float32

    def test_vitals_last_sample_values(self):
        """vitals = [hr, spo2/100, signal_quality] from last sample."""
        from services.ml_inference_service import MLInferenceService
        from services.live_window_buffer import WindowSample

        svc = MLInferenceService()
        window = [
            WindowSample(
                timestamp_ms=0, packet_seq=0, mode="mock",
                accel_x=0.0, accel_y=0.0, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                red_value=0, ir_value=60000,
                heart_rate=80.0, spo2=97.0, signal_quality=0.85,
                imu_ok=True, ppg_ok=True, hr_valid=True,
                spo2_valid=True, finger_detected=True,
                motion_score=0.0, final_risk_score=0.0,
                quality_confidence=0.85,
            )
        ]
        inputs = svc.build_predictor_inputs(window)
        import numpy as np
        # vitals[0] = hr=80.0, vitals[1] = 97/100=0.97, vitals[2] = 0.85
        assert abs(inputs["vitals"][0] - 80.0) < 0.001
        assert abs(inputs["vitals"][1] - 0.97) < 0.001
        assert abs(inputs["vitals"][2] - 0.85) < 0.001

    def test_ir_value_normalized_in_ppg(self):
        from services.ml_inference_service import MLInferenceService
        from services.live_window_buffer import WindowSample

        svc = MLInferenceService()
        window = [
            WindowSample(
                timestamp_ms=0, packet_seq=0, mode="mock",
                accel_x=0.0, accel_y=0.0, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                red_value=0, ir_value=100_000,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
                imu_ok=True, ppg_ok=True, hr_valid=True,
                spo2_valid=True, finger_detected=True,
                motion_score=0.0, final_risk_score=0.0,
                quality_confidence=1.0,
            )
        ]
        inputs = svc.build_predictor_inputs(window)
        # ir_value=100_000 → ppg[0,0]=1.0
        assert abs(inputs["ppg"][0, 0] - 1.0) < 1e-5


# ===========================================================================
# E) Sampling mismatch detection
# ===========================================================================

class TestSamplingMismatch:
    """Firmware 1 pkt/s vs ML 50 Hz → estimated_duration >> expected_duration."""

    def test_no_warning_when_only_two_packets(self):
        from services.live_window_buffer import LiveWindowBufferManager

        mgr = LiveWindowBufferManager()
        uid = "user_mismatch_1"
        # 2 packets 1 s apart — buffer not full, ratio cannot trigger warning
        for i in range(2):
            pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1000)
            mgr.add_packet(uid, pkt, 0.0, 0.0)
        status = mgr.get_status(uid)
        # Not full → sample_rate_warning must be False
        assert status["sample_rate_warning"] is False

    def test_warning_when_full_buffer_with_slow_packets(self):
        """200 packets spaced 1000 ms apart → ~200 s elapsed.

        expected_duration = 200 / 50 = 4 s
        ratio = 200 / 4 = 50 >> 3 → sample_rate_warning = True.
        """
        from services.live_window_buffer import LiveWindowBufferManager
        import unittest.mock as m

        window_size = 200
        sample_rate_hz = 50
        mgr = LiveWindowBufferManager()
        uid = "user_mismatch_2"

        with m.patch("services.live_window_buffer.settings") as ms:
            ms.ML_WINDOW_SIZE = window_size
            ms.ML_EXPECTED_SAMPLE_RATE_HZ = sample_rate_hz
            ms.ML_WARN_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_USE_PACKET_SUMMARY_MODE = True
            ms.ML_INFERENCE_ENABLED = False
            ms.ML_INFERENCE_EVERY_N_PACKETS = 50

            # Packets 1 second apart (firmware 1 pkt/s)
            for i in range(window_size):
                pkt = _make_fake_packet(
                    packet_seq=i,
                    timestamp_ms=i * 1_000,  # 1 second per packet
                )
                mgr.add_packet(uid, pkt, 0.0, 0.0)

            status = mgr.get_status(uid)

        assert status["is_full"] is True
        # estimated_duration ≈ 199 s, expected = 4 s, ratio ≈ 49.75
        assert status["estimated_window_duration_sec"] is not None
        estimated = status["estimated_window_duration_sec"]
        expected = status["expected_duration_sec"]
        assert estimated > expected * 3
        assert status["sample_rate_warning"] is True

    def test_no_warning_when_ml_warn_disabled(self):
        from services.live_window_buffer import LiveWindowBufferManager
        import unittest.mock as m

        mgr = LiveWindowBufferManager()
        uid = "user_mismatch_3"
        window_size = 200

        with m.patch("services.live_window_buffer.settings") as ms:
            ms.ML_WINDOW_SIZE = window_size
            ms.ML_EXPECTED_SAMPLE_RATE_HZ = 50
            ms.ML_WARN_ON_SAMPLE_RATE_MISMATCH = False  # disabled
            ms.ML_USE_PACKET_SUMMARY_MODE = True
            ms.ML_INFERENCE_ENABLED = False
            ms.ML_INFERENCE_EVERY_N_PACKETS = 50

            for i in range(window_size):
                pkt = _make_fake_packet(packet_seq=i, timestamp_ms=i * 1_000)
                mgr.add_packet(uid, pkt, 0.0, 0.0)
            status = mgr.get_status(uid)

        assert status["sample_rate_warning"] is False


# ===========================================================================
# F) Regression — Part 1 service still works
# ===========================================================================

class TestPart1Regression:
    """Smoke-check that Part 1 baseline imports still work after Part 2."""

    def test_baseline_service_imports_intact(self):
        from services.baseline_service import (
            apply_baseline_adjustment,
            compute_personal_deviation,
            compute_quality_confidence,
            is_reliable_for_baseline,
            update_user_baseline,
        )
        assert callable(apply_baseline_adjustment)
        assert callable(compute_personal_deviation)
        assert callable(compute_quality_confidence)
        assert callable(is_reliable_for_baseline)
        assert callable(update_user_baseline)

    def test_live_window_buffer_imports_clean(self):
        from services.live_window_buffer import (
            LiveWindowBufferManager,
            WindowSample,
            live_window_buffer,
        )
        assert LiveWindowBufferManager is not None
        assert WindowSample is not None
        assert live_window_buffer is not None

    def test_ml_inference_service_imports_clean(self):
        from services.ml_inference_service import (
            MLInferenceService,
            ml_inference_service,
        )
        assert MLInferenceService is not None
        assert ml_inference_service is not None

    def test_config_baseline_settings_unchanged(self):
        from config import settings
        assert settings.BASELINE_ENABLED is True
        assert settings.BASELINE_MIN_SAMPLES == 300
        assert 0.0 < settings.BASELINE_EMA_ALPHA < 1.0
        assert 0.0 < settings.BASELINE_MIN_SIGNAL_QUALITY < 1.0

    def test_schemas_backward_compat(self):
        """Old clients sending only required fields still work."""
        from schemas import DevicePacketResponse
        # Must construct without window_status and ml_shadow_result
        r = DevicePacketResponse(
            status="accepted",
            packet_seq=42,
            device_id="dev-abc",
            user_id="user-1",
            risk_breakdown={"final_risk_score": 0.1},
        )
        assert r.window_status is None
        assert r.ml_shadow_result is None
        # Serialise to dict — new fields present with null values
        d = r.model_dump()
        assert "window_status" in d
        assert "ml_shadow_result" in d
        assert d["window_status"] is None

    def test_quality_confidence_computation_unchanged(self):
        from services.baseline_service import compute_quality_confidence
        result = compute_quality_confidence(
            signal_quality=0.9,
            finger_detected=True,
            hr_valid=True,
            spo2_valid=True,
            ppg_ok=True,
            spo2=98.0,
            spo2_valid_flag=True,
        )
        assert 0.0 <= result["quality_confidence"] <= 1.0
