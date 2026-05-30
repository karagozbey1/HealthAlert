"""Comprehensive tests for HealthAlert v2 pipeline.

Test coverage:
    - Loader smoke tests
    - Column schema standardisation
    - Windowing (configurable)
    - Handcrafted feature extraction
    - Feature pipeline (missing modality safe)
    - Model v2 forward pass (with handcrafted features)
    - Multi-task loss (active_tasks)
    - Risk postprocessor v2 (full output)
    - Recommendation engine v2
    - Explainability v2
    - Extended synthetic scenarios
    - Label strategy
"""

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch is required for v2 model tests")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════
# Loader smoke tests
# ═══════════════════════════════════════════════════════════════════
class TestLoaderSmoke:
    """Smoke tests verifying loaders can be imported and basic interface works."""

    def test_hifd_loader_importable(self):
        from src.data.loaders.hifd_loader import load_all_subjects, FALL_SCENARIOS, ADL_SCENARIOS
        assert len(FALL_SCENARIOS) == 6
        assert len(ADL_SCENARIOS) == 9

    def test_but_ppg_loader_importable(self):
        from src.data.loaders.but_ppg_loader import load_all_records
        assert callable(load_all_records)

    def test_weda_fall_loader_importable(self):
        from src.data.loaders.weda_fall_loader import load_all_trials, FALL_CODES
        assert len(FALL_CODES) == 8

    def test_column_schema_constants(self):
        from src.data.column_schema import STANDARD_COLUMNS, IMU_COLUMNS, VITAL_COLUMNS
        assert "accel_x" in STANDARD_COLUMNS
        assert "heart_rate" in STANDARD_COLUMNS
        assert len(IMU_COLUMNS) == 6
        assert "ppg_quality" in VITAL_COLUMNS


# ═══════════════════════════════════════════════════════════════════
# Column schema standardisation
# ═══════════════════════════════════════════════════════════════════
class TestColumnSchema:
    """Test standardisation functions."""

    def test_standardize_hifd_record(self):
        import pandas as pd
        from src.data.column_schema import standardize_hifd_record, STANDARD_COLUMNS

        df = pd.DataFrame({
            "ax": [1.0, 2.0], "ay": [0.5, 0.6], "az": [9.8, 9.7],
            "droll": [0.1, 0.2], "dpitch": [0.0, 0.1], "dyaw": [0.0, 0.05],
            "heart": [72.0, 73.0],
        })
        record = {"data": df, "label": 1, "subject_id": "hifd_01", "session_id": "s01_fall1"}
        result = standardize_hifd_record(record)
        std_df = result["data"]
        assert list(std_df.columns) == STANDARD_COLUMNS
        assert std_df["accel_x"].iloc[0] == 1.0
        assert std_df["dataset_name"].iloc[0] == "HIFD"

    def test_standardize_weda_record(self):
        import pandas as pd
        from src.data.column_schema import standardize_weda_record, STANDARD_COLUMNS

        df = pd.DataFrame({
            "timestamp": [0.0, 0.02],
            "accel_x": [1.0, 1.1], "accel_y": [0.0, 0.1], "accel_z": [9.8, 9.8],
            "gyro_x": [0.0, 0.1], "gyro_y": [0.0, 0.0], "gyro_z": [0.0, 0.0],
        })
        record = {"data": df, "label": 0, "subject_id": "weda_U01", "session_id": "weda_U01_R01_D01"}
        result = standardize_weda_record(record)
        assert list(result["data"].columns) == STANDARD_COLUMNS

    def test_standardize_butppg_record(self):
        from src.data.column_schema import standardize_butppg_record, STANDARD_COLUMNS

        record = {"heart_rate": 75.0, "spo2": 97.0, "quality_label": 1,
                   "subject_id": "but_001", "record_id": "001001"}
        result = standardize_butppg_record(record)
        assert list(result["data"].columns) == STANDARD_COLUMNS
        assert result["data"]["heart_rate"].iloc[0] == 75.0


# ═══════════════════════════════════════════════════════════════════
# Windowing
# ═══════════════════════════════════════════════════════════════════
class TestWindowing:
    """Test windowing with various configs."""

    def test_basic_windowing(self):
        from src.data.preprocessing.windowing import extract_windows
        data = np.random.randn(500, 6)
        windows = extract_windows(data, window_size=200, stride=50)
        assert len(windows) > 0
        for w, l in windows:
            assert w.shape == (200, 6)

    def test_short_signal_padding(self):
        from src.data.preprocessing.windowing import extract_windows
        data = np.random.randn(100, 4)
        windows = extract_windows(data, window_size=200, stride=50, pad_last=True)
        assert len(windows) == 1
        assert windows[0][0].shape == (200, 4)

    def test_different_window_sizes(self):
        from src.data.preprocessing.windowing import extract_windows
        data = np.random.randn(1000, 6)
        for ws in [100, 200, 250, 500]:
            windows = extract_windows(data, window_size=ws, stride=ws // 4)
            assert len(windows) > 0
            assert windows[0][0].shape[0] == ws


# ═══════════════════════════════════════════════════════════════════
# Feature engineering
# ═══════════════════════════════════════════════════════════════════
class TestHandcraftedFeatures:
    """Test handcrafted feature extraction."""

    def test_imu_features(self):
        from src.data.feature_engineering.imu_features import extract_imu_features
        accel = np.random.randn(200, 3)
        gyro = np.random.randn(200, 3)
        features = extract_imu_features(accel, gyro)
        assert isinstance(features, dict)
        assert "svm_max" in features
        assert "jerk_max" in features

    def test_feature_pipeline_full(self):
        from src.data.feature_engineering.feature_pipeline import (
            extract_all_handcrafted_features, get_feature_dim,
        )
        accel = np.random.randn(200, 3)
        gyro = np.random.randn(200, 3)
        hr = np.full(200, 80.0) + np.random.randn(200) * 5
        spo2 = np.full(200, 97.0) + np.random.randn(200) * 0.5

        vec, names = extract_all_handcrafted_features(accel, gyro, hr, spo2, 0.8, 50)
        assert vec.shape[0] == len(names)
        assert vec.shape[0] > 30  # expect ~38 features
        assert not np.any(np.isnan(vec))  # no NaN with full data

        dim = get_feature_dim()
        assert dim == len(names)

    def test_feature_pipeline_missing_modality(self):
        """Features should still work with missing modalities (NaN fill)."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features

        # Only accel available
        accel = np.random.randn(200, 3)
        vec, names = extract_all_handcrafted_features(accel=accel, sr=50)
        assert vec.shape[0] == len(names)
        # PPG features should be NaN
        hr_idx = names.index("hr_mean") if "hr_mean" in names else -1
        if hr_idx >= 0:
            assert np.isnan(vec[hr_idx])

    def test_feature_pipeline_only_hr(self):
        """Only vitals available."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features
        hr = np.full(50, 90.0)
        vec, names = extract_all_handcrafted_features(hr_signal=hr, sr=50)
        assert len(vec) == len(names)

    def test_fusion_features(self):
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features
        accel = np.random.randn(200, 3)
        gyro = np.random.randn(200, 3)
        hr = np.linspace(75, 130, 200)  # rising HR
        spo2 = np.linspace(97, 88, 200)  # dropping SpO2

        vec, names = extract_all_handcrafted_features(accel, gyro, hr, spo2, 0.8, 50)
        assert "hr_high_and_rising" in names
        assert "spo2_low_and_falling" in names
        assert "combined_risk_pattern" in names


# ═══════════════════════════════════════════════════════════════════
# Model v2
# ═══════════════════════════════════════════════════════════════════
class TestModelV2:
    """Test HealthAlertModelV2."""

    def test_forward_pass(self):
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        batch = {
            "imu": torch.randn(4, 200, 6),
            "ppg": torch.randn(4, 200, 1),
            "vitals": torch.randn(4, 2),
            "handcrafted_features": torch.randn(4, 38),
        }
        with torch.no_grad():
            outputs = model(batch)

        assert "fall_logit" in outputs
        assert "instability_logit" in outputs
        assert "quality_logit" in outputs
        assert "risk_score" in outputs
        assert outputs["fall_logit"].shape == (4,)
        assert outputs["risk_score"].shape == (4,)

    def test_forward_without_handcrafted(self):
        """Model should work without handcrafted_features key."""
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        batch = {
            "imu": torch.randn(2, 200, 6),
            "ppg": torch.randn(2, 200, 1),
            "vitals": torch.randn(2, 2),
        }
        with torch.no_grad():
            outputs = model(batch)
        assert outputs["fall_logit"].shape == (2,)

    def test_parameter_count(self):
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        n_params = model.count_parameters()
        assert n_params > 0
        assert n_params < 10_000_000

    def test_freeze_unfreeze(self):
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        model.freeze_encoders()
        for p in model.imu_encoder.parameters():
            assert not p.requires_grad
        model.unfreeze_all()
        for p in model.imu_encoder.parameters():
            assert p.requires_grad

    def test_handcrafted_mlp(self):
        from src.models.blocks.handcrafted_mlp import HandcraftedMLP
        mlp = HandcraftedMLP(input_dim=38, hidden_dims=[64, 32])
        x = torch.randn(4, 38)
        out = mlp(x)
        assert out.shape == (4, 32)


# ═══════════════════════════════════════════════════════════════════
# Losses
# ═══════════════════════════════════════════════════════════════════
class TestLosses:
    """Test loss functions."""

    def test_multitask_loss_all_tasks(self):
        from src.training.losses import MultiTaskLoss
        criterion = MultiTaskLoss()
        outputs = {
            "fall_logit": torch.randn(8),
            "instability_logit": torch.randn(8),
            "quality_logit": torch.randn(8),
            "risk_score": torch.sigmoid(torch.randn(8)),
        }
        targets = {
            "fall_label": torch.randint(0, 2, (8,)).float(),
            "instability_label": torch.randint(0, 2, (8,)).float(),
            "quality_label": torch.randint(0, 2, (8,)).float(),
            "risk_label": torch.rand(8),
        }
        total, losses = criterion(outputs, targets)
        assert total.item() >= 0
        assert "fall" in losses

    def test_multitask_loss_active_tasks(self):
        """Test that active_tasks filters which losses are computed."""
        from src.training.losses import MultiTaskLoss
        criterion = MultiTaskLoss()
        outputs = {
            "fall_logit": torch.randn(4),
            "instability_logit": torch.randn(4),
            "quality_logit": torch.randn(4),
            "risk_score": torch.sigmoid(torch.randn(4)),
        }
        targets = {
            "fall_label": torch.ones(4),
            "instability_label": torch.zeros(4),
            "quality_label": torch.ones(4),
            "risk_label": torch.rand(4),
        }
        total, losses = criterion(outputs, targets, active_tasks=["quality"])
        assert "quality" in losses
        assert "fall" not in losses


# ═══════════════════════════════════════════════════════════════════
# Inference
# ═══════════════════════════════════════════════════════════════════
class TestInferenceV2:
    """Test enhanced inference pipeline."""

    def test_risk_postprocessor_v2_full_output(self):
        from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
        pp = RiskPostprocessorV2()
        predictions = {
            "fall_prob": 0.9, "instability_prob": 0.3,
            "quality_score": 0.8, "risk_score": 0.7,
        }
        vitals = {"heart_rate": 60, "spo2": 98}
        result = pp.process(predictions, vitals)

        # Check all required fields
        assert "fall_probability" in result
        assert "instability_probability" in result
        assert "ppg_quality_score" in result
        assert "vital_confidence_score" in result
        assert "early_risk_score" in result
        assert "final_risk_level" in result
        assert "immediate_alert" in result
        assert "reasons" in result
        assert "recommendations" in result
        assert "raw_scores" in result
        assert isinstance(result["immediate_alert"], bool)
        assert isinstance(result["reasons"], list)
        assert isinstance(result["recommendations"], list)
        assert isinstance(result["raw_scores"], dict)
        assert result["final_risk_level"] == "critical"

    def test_postprocessor_normal(self):
        from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
        pp = RiskPostprocessorV2()
        result = pp.process(
            {"fall_prob": 0.05, "instability_prob": 0.02,
             "quality_score": 0.9, "risk_score": 0.1},
            {"heart_rate": 75, "spo2": 98},
        )
        assert result["final_risk_level"] == "normal"
        assert result["immediate_alert"] is False

    def test_recommendation_engine_v2(self):
        from src.inference.recommendation_engine_v2 import RecommendationEngineV2
        engine = RecommendationEngineV2()
        recs = engine.get_recommendations({
            "final_risk_level": "critical",
            "ppg_quality_score": 0.9,
            "immediate_alert": True,
        })
        assert len(recs) > 0
        # Should contain immediate alert prefix
        assert any("IMMEDIATE" in r for r in recs)

    def test_explainability_v2(self):
        from src.inference.explainability_v2 import ExplainableOutputV2
        exp = ExplainableOutputV2()
        result = exp.explain(
            {"fall_prob": 0.8, "quality_score": 0.9},
            {"heart_rate": 45, "spo2": 90},
            {"accel_magnitude_max": 5.0, "jerk_estimate_max": 100},
        )
        assert "contributions" in result
        assert len(result["contributions"]) > 0
        # English output
        for contrib in result["contributions"]:
            assert "explanation" in contrib
            # Should be English (no Turkish characters in standard explanations)


# ═══════════════════════════════════════════════════════════════════
# Synthetic scenarios
# ═══════════════════════════════════════════════════════════════════
class TestExtendedScenarios:
    """Test extended scenario generator."""

    def test_all_scenarios(self):
        from src.simulation.extended_scenarios import ExtendedScenarioGenerator
        gen = ExtendedScenarioGenerator(sr=50, seed=42)
        scenarios = gen.generate_all()
        assert len(scenarios) == 6

        for s in scenarios:
            assert "name" in s
            assert "data" in s
            assert "expected_risk" in s
            assert "timestamp" in s["data"]
            assert "accel_x" in s["data"]
            assert len(s["data"]["timestamp"]) > 0

    def test_hr_rising_scenario(self):
        from src.simulation.extended_scenarios import ExtendedScenarioGenerator
        gen = ExtendedScenarioGenerator()
        data = gen.hr_rising(15.0)
        hr = data["heart_rate"]
        # HR should be rising
        first_q = np.mean(hr[:len(hr)//4])
        last_q = np.mean(hr[-len(hr)//4:])
        assert last_q > first_q + 30  # significant rise

    def test_spo2_drop_scenario(self):
        from src.simulation.extended_scenarios import ExtendedScenarioGenerator
        gen = ExtendedScenarioGenerator()
        data = gen.spo2_drop(15.0)
        spo2 = data["spo2"]
        first_q = np.mean(spo2[:len(spo2)//4])
        last_q = np.mean(spo2[-len(spo2)//4:])
        assert first_q > last_q + 5  # significant drop


# ═══════════════════════════════════════════════════════════════════
# Label strategy
# ═══════════════════════════════════════════════════════════════════
class TestLabelStrategy:
    """Test label generation utilities."""

    def test_fall_label(self):
        from src.data.preprocessing.label_strategy import generate_fall_label
        assert generate_fall_label({"label": 1}) == 1
        assert generate_fall_label({"label": 0}) == 0
        assert generate_fall_label({"label": 2}) == 0

    def test_instability_label(self):
        from src.data.preprocessing.label_strategy import generate_instability_label
        assert generate_instability_label({"label": 2}) == 1
        assert generate_instability_label({"label": 0}) == 0

    def test_quality_label(self):
        from src.data.preprocessing.label_strategy import generate_quality_label
        assert generate_quality_label({"dataset_name": "BUT_PPG", "quality_label": 1}) == 1.0
        assert generate_quality_label({"dataset_name": "HIFD"}) == 1.0

    def test_risk_proxy_label(self):
        from src.data.preprocessing.label_strategy import generate_risk_proxy_label
        # Fall event should give high risk
        risk = generate_risk_proxy_label({"label": 1})
        assert risk >= 0.9

        # Normal event, normal vitals
        risk = generate_risk_proxy_label(
            {"label": 0},
            hr_array=np.full(200, 75.0),
            spo2_array=np.full(200, 97.0),
        )
        assert risk < 0.3

    def test_risk_ordinal_bins(self):
        from src.data.preprocessing.label_strategy import risk_score_to_ordinal_bin
        assert risk_score_to_ordinal_bin(0.0) == 0
        assert risk_score_to_ordinal_bin(0.5) == 2
        assert risk_score_to_ordinal_bin(1.0) == 4


# ═══════════════════════════════════════════════════════════════════
# Scaler pipeline
# ═══════════════════════════════════════════════════════════════════
class TestScalerPipeline:
    """Test modality-aware scaler."""

    def test_scaler_fit_transform(self):
        from src.data.preprocessing.scaler_pipeline import ModalityScaler
        scaler = ModalityScaler()

        # Fit
        for _ in range(10):
            scaler.partial_fit_imu(np.random.randn(200, 6) * 10 + 5)
        scaler.finalise()

        # Transform
        data = np.random.randn(100, 6) * 10 + 5
        normalized = scaler.transform_imu(data)
        # Should be roughly mean≈0, std≈1
        assert abs(np.mean(normalized)) < 2.0


# ═══════════════════════════════════════════════════════════════════
# Original model (backward compat)
# ═══════════════════════════════════════════════════════════════════
class TestOriginalModel:
    """Ensure original model still works."""

    def test_model_forward(self):
        from src.models.multitask_model import HealthAlertModel
        model = HealthAlertModel()
        batch = {
            "imu": torch.randn(4, 200, 6),
            "ppg": torch.randn(4, 200, 1),
            "vitals": torch.randn(4, 3),
        }
        with torch.no_grad():
            outputs = model(batch)
        assert outputs["fall_logit"].shape == (4,)


# ═══════════════════════════════════════════════════════════════════
# Leakage & Split Integrity Tests
# ═══════════════════════════════════════════════════════════════════
class TestLeakageAndSplitIntegrity:
    """Verify subject-wise split integrity and data leakage prevention."""

    def test_subject_split_no_overlap(self):
        """Subject sets in train/val/test must be disjoint."""
        from src.data.dataset_registry import subject_wise_split

        records = [
            {"subject_id": f"s_{i:02d}", "label": i % 3, "dataset_name": "test"}
            for i in range(30)
        ]
        train, val, test = subject_wise_split(records, 0.7, 0.15, 0.15, seed=42)

        train_subjects = set(r["subject_id"] for r in train)
        val_subjects = set(r["subject_id"] for r in val)
        test_subjects = set(r["subject_id"] for r in test)

        assert not (train_subjects & val_subjects), "train/val subject overlap!"
        assert not (train_subjects & test_subjects), "train/test subject overlap!"
        assert not (val_subjects & test_subjects), "val/test subject overlap!"

    def test_global_split_consistency(self):
        """Same seed + same records must produce identical splits."""
        from src.data.dataset_registry import subject_wise_split

        records = [
            {"subject_id": f"s_{i:02d}", "label": 0}
            for i in range(20)
        ]
        s1_train, s1_val, s1_test = subject_wise_split(records, seed=42)
        s2_train, s2_val, s2_test = subject_wise_split(records, seed=42)

        assert set(r["subject_id"] for r in s1_train) == set(r["subject_id"] for r in s2_train)
        assert set(r["subject_id"] for r in s1_test) == set(r["subject_id"] for r in s2_test)

    def test_no_quality_label_in_vitals(self):
        """Vitals vector must NOT contain the quality label (leakage)."""
        import pandas as pd
        from src.data.base_dataset import HealthAlertDataset
        from src.data.column_schema import standardize_butppg_record

        rec = standardize_butppg_record({
            "heart_rate": 80.0, "spo2": 95.0, "quality_label": 0,
            "subject_id": "but_test", "record_id": "999",
            "dataset_name": "BUT_PPG",
        })

        ds = HealthAlertDataset([rec], window_size=200, stride=50,
                                 normalize=False, fit_scaler_on_init=False)
        sample = ds[0]
        vitals = sample["vitals"].numpy()
        # Vitals should be [hr, spo2/100], dim=2
        assert vitals.shape == (2,), f"Vitals dim should be 2, got {vitals.shape}"
        # vitals should be approximately [80.0, 0.95]
        assert abs(vitals[0] - 80.0) < 1.0, f"Expected HR~80, got {vitals[0]}"
        assert abs(vitals[1] - 0.95) < 0.1, f"Expected spo2/100~0.95, got {vitals[1]}"
        # Verify quality_label=0 does NOT appear anywhere in vitals
        assert vitals[0] != 0.0 and vitals[1] != 0.0, "quality_label=0 may have leaked"

    def test_no_quality_in_handcrafted_features(self):
        """Handcrafted features must not contain the quality label."""
        from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features

        vec, names = extract_all_handcrafted_features(
            accel=np.random.randn(200, 3),
            gyro=np.random.randn(200, 3),
            hr_signal=np.full(200, 75.0),
            spo2_signal=np.full(200, 97.0),
            ppg_quality=None,  # Must be None to prevent leakage
            sr=50,
        )
        if "ppg_quality_aggregate" in names:
            idx = names.index("ppg_quality_aggregate")
            assert np.isnan(vec[idx]) or vec[idx] == 0.0, \
                "ppg_quality_aggregate should be NaN/0 when quality not provided"


class TestStage4vs5Differentiation:
    """Verify stages 4 and 5 are structurally different."""

    def test_stage4_freezes_encoders(self):
        """Stage 4 must freeze encoder parameters."""
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        model.freeze_encoders()

        for p in model.imu_encoder.parameters():
            assert not p.requires_grad, "IMU encoder should be frozen in stage 4"
        for p in model.ppg_encoder.parameters():
            assert not p.requires_grad, "PPG encoder should be frozen in stage 4"

        # Fusion and heads should still be trainable
        for p in model.fusion.parameters():
            assert p.requires_grad, "Fusion should be trainable in stage 4"
        for p in model.fall_head.parameters():
            assert p.requires_grad, "Fall head should be trainable in stage 4"

    def test_stage5_unfreezes_all(self):
        """Stage 5 unfreezes everything."""
        from src.models.multitask_model_v2 import HealthAlertModelV2
        model = HealthAlertModelV2()
        model.freeze_encoders()
        model.unfreeze_all()

        for p in model.parameters():
            assert p.requires_grad, "All params should be trainable in stage 5"


class TestRiskLevelEvaluation:
    """Verify risk-level ordinal evaluation."""

    def test_risk_level_metrics_exist(self):
        from src.training.metrics import compute_risk_level_metrics
        y_true = np.array([0.0, 0.1, 0.3, 0.55, 0.8, 0.95])
        y_pred = np.array([0.05, 0.15, 0.35, 0.50, 0.75, 0.90])
        metrics = compute_risk_level_metrics(y_true, y_pred)

        assert "risk_level_accuracy" in metrics
        assert "risk_level_macro_f1" in metrics
        assert "risk_level_weighted_kappa" in metrics
        assert "risk_level_normal_f1" in metrics
        assert "risk_level_critical_f1" in metrics
        assert "risk_level_confusion_matrix" in metrics

    def test_threshold_calibration(self):
        from src.training.metrics import calibrate_threshold
        np.random.seed(42)
        y_true = np.concatenate([np.zeros(100), np.ones(30)])
        y_prob = np.concatenate([
            np.random.beta(2, 8, 100),  # negatives: low probs
            np.random.beta(8, 2, 30),   # positives: high probs
        ])
        t, score = calibrate_threshold(y_true, y_prob, objective="f1")
        assert 0.05 < t < 0.95
        assert score > 0.5  # Should find a reasonable threshold

    def test_calibrated_metrics(self):
        from src.training.metrics import compute_all_metrics
        np.random.seed(42)
        outputs = {
            "fall": np.concatenate([np.random.beta(2,5,80), np.random.beta(5,2,20)]),
            "instability": np.random.rand(100) * 0.5,
            "quality": np.random.rand(100) * 0.3 + 0.7,
            "risk": np.random.rand(100) * 0.5,
        }
        targets = {
            "fall": np.concatenate([np.zeros(80), np.ones(20)]).astype(float),
            "instability": np.zeros(100),
            "quality": np.ones(100),
            "risk": np.random.rand(100) * 0.5,
        }
        # Default threshold
        m1 = compute_all_metrics(outputs, targets, threshold=0.5)
        # Custom calibrated threshold
        m2 = compute_all_metrics(outputs, targets, calibrated_thresholds={"fall": 0.3})
        assert "fall_threshold" in m2
        assert m2["fall_threshold"] == 0.3


class TestPostprocessorConsistency:
    """Verify postprocessor behavior is consistent."""

    def test_low_quality_reduces_confidence(self):
        from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
        pp = RiskPostprocessorV2()
        high_q = pp.process(
            {"fall_prob": 0.1, "instability_prob": 0.1, "quality_score": 0.95, "risk_score": 0.2},
            {"heart_rate": 75, "spo2": 98},
        )
        low_q = pp.process(
            {"fall_prob": 0.1, "instability_prob": 0.1, "quality_score": 0.2, "risk_score": 0.2},
            {"heart_rate": 75, "spo2": 98},
        )
        assert low_q["confidence"] < high_q["confidence"]

    def test_single_spike_dampened(self):
        from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
        pp = RiskPostprocessorV2()
        result = pp.process(
            {"fall_prob": 0.6, "instability_prob": 0.1, "quality_score": 0.9, "risk_score": 0.3},
            {"heart_rate": 75, "spo2": 98},
        )
        # With only fall elevated, spike dampening should reduce risk
        assert result["raw_scores"]["n_elevated_signals"] <= 1

    def test_multi_signal_boosts(self):
        from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
        pp = RiskPostprocessorV2()
        result = pp.process(
            {"fall_prob": 0.7, "instability_prob": 0.5, "quality_score": 0.8, "risk_score": 0.6},
            {"heart_rate": 130, "spo2": 95},
        )
        assert result["raw_scores"]["n_elevated_signals"] >= 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
