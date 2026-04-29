"""Unit tests for HealthAlert core modules."""

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch is required for model tests")

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIMUFeatures:
    """Test IMU feature extraction."""

    def test_svm(self):
        from src.data.feature_engineering.imu_features import compute_svm
        accel = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 9.81]])
        svm = compute_svm(accel)
        assert len(svm) == 3
        np.testing.assert_almost_equal(svm[0], 1.0)
        np.testing.assert_almost_equal(svm[2], 9.81, decimal=2)

    def test_jerk(self):
        from src.data.feature_engineering.imu_features import compute_jerk
        accel = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
        jerk = compute_jerk(accel, sr=50)
        assert jerk.shape == (2, 3)
        np.testing.assert_almost_equal(jerk[0, 0], 50.0)

    def test_tilt_angle(self):
        from src.data.feature_engineering.imu_features import compute_tilt_angle
        accel = np.array([[0, 0, 9.81], [9.81, 0, 0]])
        tilt = compute_tilt_angle(accel)
        assert tilt[0] < 5  # Nearly vertical
        assert 85 < tilt[1] < 95  # Nearly horizontal

    def test_extract_imu_features(self):
        from src.data.feature_engineering.imu_features import extract_imu_features
        accel = np.random.randn(200, 3)
        gyro = np.random.randn(200, 3)
        features = extract_imu_features(accel, gyro)
        assert isinstance(features, dict)
        assert "svm_max" in features
        assert "jerk_max" in features
        assert "tilt_mean" in features


class TestModel:
    """Test model forward pass."""

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

        assert "fall_logit" in outputs
        assert "instability_logit" in outputs
        assert "quality_logit" in outputs
        assert "risk_score" in outputs
        assert outputs["fall_logit"].shape == (4,)
        assert outputs["risk_score"].shape == (4,)

    def test_model_parameter_count(self):
        from src.models.multitask_model import HealthAlertModel
        model = HealthAlertModel()
        n_params = model.count_parameters()
        assert n_params > 0
        assert n_params < 10_000_000  # Reasonable size

    def test_imu_encoder(self):
        from src.models.blocks.imu_encoder import IMUEncoder
        enc = IMUEncoder(in_channels=6)
        x = torch.randn(2, 200, 6)
        out = enc(x)
        assert out.shape == (2, enc.output_dim)

    def test_ppg_encoder(self):
        from src.models.blocks.ppg_encoder import PPGEncoder
        enc = PPGEncoder(in_channels=1)
        x = torch.randn(2, 200, 1)
        out = enc(x)
        assert out.shape == (2, enc.output_dim)

    def test_quality_gate(self):
        from src.models.blocks.quality_gate import QualityGate
        gate = QualityGate(ppg_dim=64, quality_input_dim=2)
        ppg_embed = torch.randn(2, 64)
        quality_in = torch.randn(2, 2)
        gated, score = gate(ppg_embed, quality_in)
        assert gated.shape == (2, 64)
        assert score.shape == (2, 1)
        assert (score >= 0).all() and (score <= 1).all()


class TestPreprocessing:
    """Test preprocessing modules."""

    def test_windowing(self):
        from src.data.preprocessing.windowing import extract_windows
        data = np.random.randn(500, 6)
        windows = extract_windows(data, window_size=200, stride=50)
        assert len(windows) > 0
        for w, l in windows:
            assert w.shape == (200, 6)

    def test_normalization(self):
        from src.data.preprocessing.normalization import StandardScaler
        scaler = StandardScaler()
        data = np.random.randn(100, 6) * 10 + 5
        normalized = scaler.fit_transform(data)
        np.testing.assert_almost_equal(np.mean(normalized, axis=0), 0, decimal=5)
        np.testing.assert_almost_equal(np.std(normalized, axis=0), 1, decimal=5)

    def test_robust_normalize(self):
        from src.data.preprocessing.normalization import robust_normalize
        data = np.random.randn(100, 3) * 100
        data[0, 0] = 1e6  # Outlier
        normalized = robust_normalize(data, clip_std=3.0)
        assert np.abs(normalized).max() <= 3.0 + 1e-6

    def test_resampling(self):
        from src.data.preprocessing.resampling import resample_uniform
        timestamps = np.sort(np.random.uniform(0, 10, 200))
        signal = np.sin(timestamps)
        resampled = resample_uniform(signal, timestamps, target_sr=50)
        assert len(resampled) > 0


class TestLosses:
    """Test loss functions."""

    def test_focal_loss(self):
        from src.training.losses import FocalLoss
        loss = FocalLoss()
        logits = torch.randn(10)
        targets = torch.randint(0, 2, (10,)).float()
        l = loss(logits, targets)
        assert l.item() >= 0

    def test_multitask_loss(self):
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


class TestInference:
    """Test inference pipeline."""

    def test_postprocessor(self):
        from src.inference.risk_postprocessor import RiskPostprocessor
        pp = RiskPostprocessor()
        predictions = {"fall_prob": 0.9, "instability_prob": 0.3, "quality_score": 0.8, "risk_score": 0.7}
        vitals = {"heart_rate": 60, "spo2": 98}
        result = pp.process(predictions, vitals)
        assert result["final_risk_level"] == "critical"
        assert 0 <= result["early_risk_score"] <= 1

    def test_recommendation_engine(self):
        from src.inference.recommendation_engine import RecommendationEngine
        engine = RecommendationEngine()
        recs = engine.get_recommendations({"final_risk_level": "critical", "ppg_quality_score": 0.9})
        assert len(recs) > 0

    def test_explainability(self):
        from src.inference.explainability import ExplainableOutput
        exp = ExplainableOutput()
        result = exp.explain(
            {"fall_prob": 0.8, "quality_score": 0.9},
            {"heart_rate": 45, "spo2": 90},
            {"svm_max": 5.0, "jerk_max": 100},
        )
        assert "contributions" in result
        assert len(result["contributions"]) > 0


class TestSimulation:
    """Test synthetic data generation."""

    def test_normal_stream(self):
        from src.simulation.synthetic_stream import SyntheticStream
        stream = SyntheticStream()
        data = stream.generate_normal(5.0)
        assert "timestamp" in data
        assert "accel_x" in data
        assert len(data["timestamp"]) == 250  # 5s * 50Hz

    def test_fall_stream(self):
        from src.simulation.synthetic_stream import SyntheticStream
        stream = SyntheticStream()
        data = stream.generate_fall(10.0, fall_time=5.0)
        svm = np.sqrt(data["accel_x"]**2 + data["accel_y"]**2 + data["accel_z"]**2)
        assert np.max(svm) > 15  # Fall should have high acceleration

    def test_streaming(self):
        from src.simulation.synthetic_stream import SyntheticStream
        stream = SyntheticStream()
        windows = list(stream.generate_stream("normal", 10, 200, 100))
        assert len(windows) > 0
        assert len(windows[0]["accel_x"]) == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
