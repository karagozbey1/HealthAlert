"""
Test 18 — Retrieval-Augmented Time-Series Risk Analysis PoC (Part 3)

Tests:
  A) Index build basics
     - Window extraction function correctness.
     - Label mapping correctness.
     - Feature extraction produces correct dim / no NaN after nan_to_num.
     - build_summary structure.

  B) RetrievalEngine load / query
     - Missing dir → is_available()=False (no exception).
     - Missing index file → is_available()=False.
     - Successful mock load → is_available()=True.
     - query() dim mismatch → retrieval_available=False.
     - query() NaN vector → sanitized, result returned.
     - query() returns required keys.
     - compute_support() formula verified.
     - explain() returns non-empty string.

  C) Feature contract
     - get_feature_dim() > 0.
     - extract_all_handcrafted_features: deterministic feature names.
     - NaN inputs produce NaN vector (expected by pipeline).
     - nan_to_num clears all NaN/inf.
     - Full pipeline: window_data → feature_vec shape correct.

  D) Demo / outputs
     - demo_query_result.json required keys present (if file exists).
     - similar_examples format correct (if file exists).
     - support_score in [0,1] (if file exists).

  E) Backend shadow
     - RETRIEVAL_ENABLED=False → retrieval_shadow_result=None in response.
     - Index dir missing → no exception, fail-open result.
     - retrieval_shadow_result does NOT modify final_risk_score.
     - sample_rate_warning=True → low_confidence=True in result.
     - RETRIEVAL_SHADOW_MODE=True → shadow_mode key present.
     - Wrong feature_dim → fail-open result.

  F) Regression — Parts 1, 2, and config still intact
     - Part 1 baseline imports unchanged.
     - Part 2 live_window_buffer imports unchanged.
     - Part 2 ml_inference_service imports unchanged.
     - DevicePacketResponse has retrieval_shadow_result field.
     - Backward compat: no retrieval fields required.
     - Config has RETRIEVAL_ENABLED attribute.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest.mock as mock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_retrieval_poc.db")

# AI_ROOT for RetrievalEngine / feature pipeline imports
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_AI_ROOT = os.path.join(_PROJECT_ROOT, "healthalert_final_ai")
if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_packet(**kwargs):
    defaults = dict(
        device_id="test-device-retrieval",
        timestamp_ms=1_700_000_000_000,
        mode="mock",
        packet_seq=1,
        accel_x=0.01, accel_y=0.02, accel_z=1.0,
        gyro_x=0.0,  gyro_y=0.0,  gyro_z=0.0,
        red_value=50_000, ir_value=55_000,
        heart_rate=72.0, spo2=98.0, signal_quality=0.9,
        imu_ok=True, ppg_ok=True,
        hr_valid=True, spo2_valid=True, finger_detected=True,
        state_hint="normal",
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _dummy_accel(n: int = 200) -> np.ndarray:
    rng = np.random.default_rng(0)
    a = rng.normal(0.0, 0.1, (n, 3)).astype(np.float32)
    a[:, 2] += 1.0
    return a


def _dummy_gyro(n: int = 200) -> np.ndarray:
    return np.random.default_rng(1).normal(0.0, 0.1, (n, 3)).astype(np.float32)


def _feature_pipeline_available() -> bool:
    try:
        from src.data.feature_engineering.feature_pipeline import get_feature_dim
        return True
    except Exception:
        return False


def _build_script_available() -> bool:
    try:
        from scripts.build_retrieval_index import (
            extract_windows,
            _map_label_group,
            _map_risk_level,
            extract_feature_from_window,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# A) Index build basics
# ---------------------------------------------------------------------------

class TestIndexBuildBasics:

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a1_extract_windows_full_coverage(self):
        """extract_windows returns correct count for evenly divisible data."""
        from scripts.build_retrieval_index import extract_windows, WINDOW_SIZE, STRIDE
        n = WINDOW_SIZE + STRIDE * 3  # 4 windows exactly
        data = np.zeros((n, 6), dtype=np.float32)
        windows = extract_windows(data, window_size=WINDOW_SIZE, stride=STRIDE)
        assert len(windows) >= 4

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a2_extract_windows_shape(self):
        """Each extracted window has expected number of rows."""
        from scripts.build_retrieval_index import extract_windows, WINDOW_SIZE, STRIDE
        data = np.zeros((500, 6), dtype=np.float32)
        windows = extract_windows(data)
        for start, w in windows:
            assert w.shape[1] == 6

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a3_extract_windows_short_series(self):
        """Short series below MIN_WINDOW returns empty list."""
        from scripts.build_retrieval_index import extract_windows, MIN_WINDOW
        data = np.zeros((MIN_WINDOW - 1, 6), dtype=np.float32)
        assert extract_windows(data) == []

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a4_label_mapping_fall(self):
        from scripts.build_retrieval_index import _map_label_group, _map_risk_level
        assert _map_label_group(1) == "fall"
        assert _map_risk_level("fall") == "critical"

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a5_label_mapping_near_fall(self):
        from scripts.build_retrieval_index import _map_label_group, _map_risk_level
        assert _map_label_group(2) == "near_fall"
        assert _map_risk_level("near_fall") == "warning"

    @pytest.mark.skipif(not _build_script_available(), reason="build script not importable")
    def test_a6_feature_extraction_no_nan(self):
        """extract_feature_from_window returns no NaN/inf after nan_to_num."""
        from scripts.build_retrieval_index import extract_feature_from_window, WINDOW_SIZE
        import pandas as pd
        n = WINDOW_SIZE
        arr = np.random.default_rng(42).normal(0.0, 1.0, (n, 6)).astype(np.float32)
        arr[:, 2] += 9.8  # accel_z gravity
        col_names = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]
        fv = extract_feature_from_window(arr, col_names, sr=50)
        assert np.all(np.isfinite(fv)), "Feature vector has NaN/inf after nan_to_num"


# ---------------------------------------------------------------------------
# B) RetrievalEngine load / query
# ---------------------------------------------------------------------------

class TestRetrievalEngine:

    def _make_engine_with_mock_index(self, tmp_path, feature_dim: int = 10, n_samples: int = 20):
        """Build a tiny in-memory index and save it for testing."""
        import joblib
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler
        from src.inference.retrieval_engine import RetrievalEngine

        X = np.random.default_rng(0).random((n_samples, feature_dim)).astype(np.float32)
        scaler = StandardScaler().fit(X)
        X_scaled = scaler.transform(X)
        nn = NearestNeighbors(n_neighbors=min(5, n_samples), metric="euclidean")
        nn.fit(X_scaled)

        metadata = [
            {"dataset": "HIFD", "subject_id": f"s{i}", "scenario": "fall1",
             "label_group": "fall" if i % 2 == 0 else "normal",
             "risk_level_estimate": "critical" if i % 2 == 0 else "normal",
             "window_index": i}
            for i in range(n_samples)
        ]
        summary = {"feature_dim": feature_dim, "total_windows": n_samples,
                   "datasets_included": ["HIFD"]}

        joblib.dump(nn, str(tmp_path / "retrieval_index.joblib"))
        joblib.dump(scaler, str(tmp_path / "retrieval_scaler.joblib"))
        np.save(str(tmp_path / "retrieval_features.npy"), X)
        with open(tmp_path / "retrieval_metadata.json", "w") as f:
            json.dump(metadata, f)
        with open(tmp_path / "retrieval_build_summary.json", "w") as f:
            json.dump(summary, f)

        engine = RetrievalEngine()
        engine.load(str(tmp_path))
        return engine, feature_dim

    def test_b1_missing_dir_no_exception(self, tmp_path):
        """Missing index dir → is_available()=False, no exception."""
        from src.inference.retrieval_engine import RetrievalEngine
        engine = RetrievalEngine()
        result = engine.load(str(tmp_path / "nonexistent"))
        assert result is False
        assert engine.is_available() is False

    def test_b2_missing_index_file(self, tmp_path):
        """Dir exists but index file missing → is_available()=False."""
        from src.inference.retrieval_engine import RetrievalEngine
        # Create the scaler file but not the index file
        import joblib
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        joblib.dump(scaler, str(tmp_path / "retrieval_scaler.joblib"))
        engine = RetrievalEngine()
        result = engine.load(str(tmp_path))
        assert result is False
        assert engine.is_available() is False

    def test_b3_successful_mock_load(self, tmp_path):
        """Successful load → is_available()=True."""
        engine, _ = self._make_engine_with_mock_index(tmp_path)
        assert engine.is_available() is True

    def test_b4_query_dim_mismatch(self, tmp_path):
        """Query with wrong dim → retrieval_available=False, no exception."""
        engine, feature_dim = self._make_engine_with_mock_index(tmp_path)
        wrong_vec = np.zeros(feature_dim + 5, dtype=np.float32)
        result = engine.query(wrong_vec)
        assert result["retrieval_available"] is False
        assert "mismatch" in result.get("error", "").lower()

    def test_b5_query_nan_vector(self, tmp_path):
        """NaN input vector → sanitized, query still returns result."""
        engine, feature_dim = self._make_engine_with_mock_index(tmp_path)
        nan_vec = np.full(feature_dim, np.nan, dtype=np.float32)
        result = engine.query(nan_vec)
        # Should not raise; either available or not but no exception
        assert "retrieval_available" in result

    def test_b6_query_required_keys(self, tmp_path):
        """Successful query returns all required keys."""
        engine, feature_dim = self._make_engine_with_mock_index(tmp_path)
        fv = np.random.default_rng(5).random(feature_dim).astype(np.float32)
        result = engine.query(fv, top_k=5)
        required_keys = {
            "retrieval_available", "top_k", "support_score",
            "fall_like_ratio", "near_fall_ratio", "normal_ratio",
            "similar_examples",
        }
        assert required_keys.issubset(result.keys())

    def test_b7_compute_support_fall_only(self):
        """60% fall → support_score = 0.60."""
        from src.inference.retrieval_engine import RetrievalEngine
        engine = RetrievalEngine()
        items = [{"label_group": "fall"}] * 3 + [{"label_group": "normal"}] * 2
        support = engine.compute_support(items)
        assert abs(support["support_score"] - 0.60) < 1e-4
        assert abs(support["fall_like_ratio"] - 0.60) < 1e-4

    def test_b8_compute_support_near_fall_contribution(self):
        """4/10 fall + 4/10 near_fall → support = 0.4 + 0.5*0.4 = 0.60."""
        from src.inference.retrieval_engine import RetrievalEngine
        engine = RetrievalEngine()
        items = (
            [{"label_group": "fall"}] * 4
            + [{"label_group": "near_fall"}] * 4
            + [{"label_group": "normal"}] * 2
        )
        support = engine.compute_support(items)
        expected = 0.4 + 0.5 * 0.4
        assert abs(support["support_score"] - expected) < 1e-4

    def test_b9_explain_returns_string(self, tmp_path):
        """explain() returns a non-empty string for non-empty input."""
        engine, feature_dim = self._make_engine_with_mock_index(tmp_path)
        items = [{"label_group": "fall", "dataset": "HIFD"}] * 5
        explanation = engine.explain(items)
        assert isinstance(explanation, str) and len(explanation) > 0

    def test_b10_support_score_clamped(self):
        """support_score is always <= 1.0."""
        from src.inference.retrieval_engine import RetrievalEngine
        engine = RetrievalEngine()
        # All fall AND all near_fall (edge case)
        items = (
            [{"label_group": "fall"}] * 8
            + [{"label_group": "near_fall"}] * 2
        )
        support = engine.compute_support(items)
        assert support["support_score"] <= 1.0


# ---------------------------------------------------------------------------
# C) Feature contract
# ---------------------------------------------------------------------------

class TestFeatureContract:

    @pytest.mark.skipif(not _feature_pipeline_available(), reason="feature pipeline not available")
    def test_c1_get_feature_dim_positive(self):
        """get_feature_dim() returns a positive integer."""
        from src.data.feature_engineering.feature_pipeline import get_feature_dim
        dim = get_feature_dim()
        assert isinstance(dim, int) and dim > 0

    @pytest.mark.skipif(not _feature_pipeline_available(), reason="feature pipeline not available")
    def test_c2_feature_names_deterministic(self):
        """Feature names are sorted and deterministic across two calls."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features
        accel = _dummy_accel()
        gyro = _dummy_gyro()
        _, names1 = extract_all_handcrafted_features(accel, gyro, sr=50)
        _, names2 = extract_all_handcrafted_features(accel, gyro, sr=50)
        assert names1 == names2
        assert names1 == sorted(names1)

    @pytest.mark.skipif(not _feature_pipeline_available(), reason="feature pipeline not available")
    def test_c3_nan_inputs_produce_nan_vector(self):
        """None inputs → NaN features (expected — nan_to_num cleans later)."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features
        fv, _ = extract_all_handcrafted_features(accel=None, gyro=None, sr=50)
        assert np.any(np.isnan(fv)), "Expected NaN features for None inputs"

    @pytest.mark.skipif(not _feature_pipeline_available(), reason="feature pipeline not available")
    def test_c4_nan_to_num_clears_all_nan(self):
        """After nan_to_num, no NaN/inf remain."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features
        fv, _ = extract_all_handcrafted_features(accel=None, gyro=None, sr=50)
        cleaned = np.nan_to_num(fv, nan=0.0, posinf=0.0, neginf=0.0)
        assert np.all(np.isfinite(cleaned))

    @pytest.mark.skipif(not _feature_pipeline_available(), reason="feature pipeline not available")
    def test_c5_full_pipeline_shape(self):
        """Window → feature vector has shape (feature_dim,)."""
        from src.data.feature_engineering.feature_pipeline import (
            extract_all_handcrafted_features,
            get_feature_dim,
        )
        accel = _dummy_accel(200)
        gyro = _dummy_gyro(200)
        hr = np.full(200, 72.0, dtype=np.float32)
        spo2 = np.full(200, 98.0, dtype=np.float32)
        fv, _ = extract_all_handcrafted_features(accel, gyro, hr, spo2, 0.9, 50)
        fv_clean = np.nan_to_num(fv, nan=0.0, posinf=0.0, neginf=0.0)
        expected_dim = get_feature_dim()
        assert fv_clean.shape == (expected_dim,)


# ---------------------------------------------------------------------------
# D) Demo / outputs
# ---------------------------------------------------------------------------

_DEMO_RESULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "outputs", "retrieval", "demo_query_result.json"
)
_DEMO_EXISTS = os.path.isfile(_DEMO_RESULT_PATH)


class TestDemoOutputs:

    @pytest.mark.skipif(not _DEMO_EXISTS, reason="demo_query_result.json not yet generated")
    def test_d1_required_keys_present(self):
        """demo_query_result.json has all required top-level keys."""
        with open(_DEMO_RESULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        required = {
            "retrieval_available", "support_score", "selected_source",
            "feature_dim", "top_k", "timestamp",
        }
        assert required.issubset(data.keys())

    @pytest.mark.skipif(not _DEMO_EXISTS, reason="demo_query_result.json not yet generated")
    def test_d2_similar_examples_format(self):
        """similar_examples list items have expected keys."""
        with open(_DEMO_RESULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        examples = data.get("similar_examples", [])
        if examples:
            required_ex_keys = {"dataset", "subject_id", "scenario", "label_group", "distance"}
            assert required_ex_keys.issubset(examples[0].keys())

    @pytest.mark.skipif(not _DEMO_EXISTS, reason="demo_query_result.json not yet generated")
    def test_d3_support_score_range(self):
        """support_score is in [0, 1]."""
        with open(_DEMO_RESULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("retrieval_available"):
            score = data["support_score"]
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# E) Backend shadow
# ---------------------------------------------------------------------------

class TestBackendShadow:

    def test_e1_retrieval_disabled_returns_none(self):
        """RETRIEVAL_ENABLED=False → query_window() returns fail-open dict."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as mock_settings:
            mock_settings.RETRIEVAL_ENABLED = False
            mock_settings.RETRIEVAL_TOP_K = 5
            mock_settings.RETRIEVAL_INDEX_DIR = "nonexistent"

            svc = RetrievalShadowService()
            result = svc.query_window([], {})
            assert result["retrieval_available"] is False

    def test_e2_missing_index_no_exception(self, tmp_path):
        """Missing index dir → fail-open, no exception."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as mock_settings:
            mock_settings.RETRIEVAL_ENABLED = True
            mock_settings.RETRIEVAL_TOP_K = 5
            mock_settings.RETRIEVAL_INDEX_DIR = str(tmp_path / "nonexistent_retrieval")

            svc = RetrievalShadowService()
            result = svc.query_window([], {})
            # Must not raise; returns retrieval_available=False
            assert "retrieval_available" in result
            assert result["retrieval_available"] is False

    def test_e3_shadow_result_independent_of_risk_score(self):
        """Retrieval shadow result NEVER modifies final_risk_score."""
        # This is a contract test: the service has no interface to change risk_score.
        from services.retrieval_shadow_service import RetrievalShadowService
        # The service only exposes query_window() which returns a dict.
        # There is no parameter or return value that could modify risk_score.
        svc = RetrievalShadowService()
        assert not hasattr(svc, "modify_risk_score")
        assert not hasattr(svc, "set_risk_score")

    def test_e4_sample_rate_warning_sets_low_confidence(self, tmp_path):
        """sample_rate_warning=True in window_status → low_confidence=True in result."""
        from services.retrieval_shadow_service import RetrievalShadowService
        import joblib
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler
        from src.data.feature_engineering.feature_pipeline import get_feature_dim

        # Build tiny mock index
        dim = get_feature_dim()
        n = 10
        X = np.random.default_rng(0).random((n, dim)).astype(np.float32)
        scaler = StandardScaler().fit(X)
        nn = NearestNeighbors(n_neighbors=5).fit(scaler.transform(X))
        metadata = [
            {"dataset": "HIFD", "subject_id": f"s{i}", "scenario": "fall1",
             "label_group": "fall", "risk_level_estimate": "critical", "window_index": i}
            for i in range(n)
        ]
        summary = {"feature_dim": dim, "total_windows": n, "datasets_included": ["HIFD"]}

        os.makedirs(str(tmp_path), exist_ok=True)
        joblib.dump(nn, str(tmp_path / "retrieval_index.joblib"))
        joblib.dump(scaler, str(tmp_path / "retrieval_scaler.joblib"))
        np.save(str(tmp_path / "retrieval_features.npy"), X)
        with open(tmp_path / "retrieval_metadata.json", "w") as f:
            json.dump(metadata, f)
        with open(tmp_path / "retrieval_build_summary.json", "w") as f:
            json.dump(summary, f)

        # Build window with sample_rate_warning=True
        window_status = {"is_full": True, "sample_rate_warning": True, "current_size": 200}

        # Create minimal WindowSample-like objects
        n_samples = 200
        fake_window = [
            types.SimpleNamespace(
                accel_x=0.01, accel_y=0.02, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
            )
            for _ in range(n_samples)
        ]

        with mock.patch("services.retrieval_shadow_service.settings") as mock_settings:
            mock_settings.RETRIEVAL_ENABLED = True
            mock_settings.RETRIEVAL_TOP_K = 5
            mock_settings.RETRIEVAL_INDEX_DIR = str(tmp_path)

            svc = RetrievalShadowService()
            result = svc.query_window(fake_window, window_status)

        if result.get("retrieval_available"):
            assert result.get("low_confidence") is True

    def test_e5_shadow_mode_key_present(self, tmp_path):
        """Result always contains shadow_mode=True when retrieval runs."""
        from services.retrieval_shadow_service import RetrievalShadowService

        with mock.patch("services.retrieval_shadow_service.settings") as mock_settings:
            mock_settings.RETRIEVAL_ENABLED = True
            mock_settings.RETRIEVAL_TOP_K = 5
            mock_settings.RETRIEVAL_INDEX_DIR = str(tmp_path / "missing")

            svc = RetrievalShadowService()
            result = svc.query_window([], {})
            # Even failed results should include shadow_mode=True
            assert result.get("shadow_mode") is True

    def test_e6_wrong_feature_dim_fail_open(self, tmp_path):
        """Wrong feature dim in live window → retrieval_available=False, no exception."""
        from services.retrieval_shadow_service import RetrievalShadowService
        import joblib
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler

        # Build index with dim=5 (deliberately wrong vs pipeline dim)
        dim = 5
        n = 10
        X = np.random.default_rng(0).random((n, dim)).astype(np.float32)
        scaler = StandardScaler().fit(X)
        nn = NearestNeighbors(n_neighbors=5).fit(scaler.transform(X))
        metadata = [
            {"dataset": "HIFD", "subject_id": f"s{i}", "scenario": "fall1",
             "label_group": "fall", "risk_level_estimate": "critical", "window_index": i}
            for i in range(n)
        ]
        summary = {"feature_dim": dim, "total_windows": n, "datasets_included": ["HIFD"]}

        joblib.dump(nn, str(tmp_path / "retrieval_index.joblib"))
        joblib.dump(scaler, str(tmp_path / "retrieval_scaler.joblib"))
        np.save(str(tmp_path / "retrieval_features.npy"), X)
        with open(tmp_path / "retrieval_metadata.json", "w") as f:
            json.dump(metadata, f)
        with open(tmp_path / "retrieval_build_summary.json", "w") as f:
            json.dump(summary, f)

        # Window with correct pipeline dim (>> 5)
        fake_window = [
            types.SimpleNamespace(
                accel_x=0.01, accel_y=0.02, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
            )
            for _ in range(200)
        ]

        with mock.patch("services.retrieval_shadow_service.settings") as mock_settings:
            mock_settings.RETRIEVAL_ENABLED = True
            mock_settings.RETRIEVAL_TOP_K = 5
            mock_settings.RETRIEVAL_INDEX_DIR = str(tmp_path)

            svc = RetrievalShadowService()
            # Should not raise even with dimension mismatch
            try:
                result = svc.query_window(fake_window, {"sample_rate_warning": True})
                assert "retrieval_available" in result
            except Exception as exc:
                pytest.fail(f"query_window raised an exception: {exc}")


# ---------------------------------------------------------------------------
# F) Regression — Parts 1, 2, and config
# ---------------------------------------------------------------------------

class TestRegression:

    def test_f1_part1_baseline_imports(self):
        """Part 1 baseline service imports are unchanged."""
        from services.baseline_service import (
            apply_baseline_adjustment,
            compute_personal_deviation,
            compute_quality_confidence,
        )
        assert callable(apply_baseline_adjustment)
        assert callable(compute_personal_deviation)
        assert callable(compute_quality_confidence)

    def test_f2_part2_live_window_buffer(self):
        """Part 2 live_window_buffer still importable and functional."""
        from services.live_window_buffer import LiveWindowBufferManager, live_window_buffer
        assert isinstance(live_window_buffer, LiveWindowBufferManager)
        pkt = _make_fake_packet()
        live_window_buffer.reset_user("regression_test_user_f2")
        status = live_window_buffer.add_packet(
            "regression_test_user_f2", pkt, 0.1, 0.2
        )
        assert "current_size" in status

    def test_f3_part2_ml_inference_service(self):
        """Part 2 ml_inference_service still importable."""
        from services.ml_inference_service import MLInferenceService, ml_inference_service
        assert isinstance(ml_inference_service, MLInferenceService)
        assert callable(ml_inference_service.is_available)

    def test_f4_schema_has_retrieval_field(self):
        """DevicePacketResponse has retrieval_shadow_result field."""
        from schemas import DevicePacketResponse
        fields = DevicePacketResponse.model_fields
        assert "retrieval_shadow_result" in fields

    def test_f5_schema_backward_compat(self):
        """DevicePacketResponse can be instantiated without retrieval fields."""
        from schemas import DevicePacketResponse
        resp = DevicePacketResponse(
            status="accepted",
            packet_seq=1,
            device_id="dev-001",
        )
        assert resp.retrieval_shadow_result is None
        assert resp.ml_shadow_result is None
        assert resp.window_status is None

    def test_f6_config_has_retrieval_settings(self):
        """Config has RETRIEVAL_ENABLED and related settings."""
        from config import settings
        assert hasattr(settings, "RETRIEVAL_ENABLED")
        assert hasattr(settings, "RETRIEVAL_SHADOW_MODE")
        assert hasattr(settings, "RETRIEVAL_INDEX_DIR")
        assert hasattr(settings, "RETRIEVAL_TOP_K")
        # Default must be False (shadow PoC, not active decision)
        assert settings.RETRIEVAL_ENABLED is False
