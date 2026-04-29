"""Real-time predictor for streaming inference."""

import logging
from typing import Dict, Optional

import numpy as np
import torch

from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features

logger = logging.getLogger("healthalert.inference.predictor")


class HealthAlertPredictor:
    """Real-time inference engine for HealthAlert.

    Accepts raw sensor windows and produces risk assessments.
    Supports EMA smoothing for stable output.
    """

    def __init__(
        self,
        model: torch.nn.Module,
        device: torch.device,
        ema_alpha: float = 0.3,
    ):
        self.model = model
        self.model.eval()
        self.device = device
        self.ema_alpha = ema_alpha

        # EMA state
        self._ema_state = {
            "fall_prob": 0.0,
            "instability_prob": 0.0,
            "quality_score": 1.0,
            "risk_score": 0.0,
        }

    @torch.no_grad()
    def predict(
        self,
        imu: np.ndarray,
        ppg: np.ndarray,
        vitals: np.ndarray,
        smooth: bool = True,
    ) -> Dict[str, float]:
        """Run inference on a single window.

        Args:
            imu: (T, 6) IMU array.
            ppg: (T, 1) PPG array.
            vitals: (3,) vitals vector [hr, spo2_norm, quality].
            smooth: Apply EMA smoothing.

        Returns:
            Dict with all prediction outputs.
        """
        # Build handcrafted branch input for fusion parity with training.
        spo2_scalar = float(vitals[1] * 100.0) if vitals.shape[0] > 1 else 98.0
        quality_scalar = float(vitals[2]) if vitals.shape[0] > 2 else 1.0
        hc_vec, _ = extract_all_handcrafted_features(
            accel=imu[:, :3] if imu.shape[1] >= 3 else None,
            gyro=imu[:, 3:6] if imu.shape[1] >= 6 else None,
            hr_signal=ppg[:, 0] if ppg.shape[1] >= 1 else None,
            spo2_signal=np.full(imu.shape[0], spo2_scalar, dtype=np.float32),
            ppg_quality=quality_scalar,
            sr=50,
        )

        modality_mask = np.array(
            [
                float(np.any(np.abs(imu) > 1e-8)),
                float(np.any(np.abs(ppg) > 1e-8)),
                float(np.any(np.abs(vitals) > 1e-8)),
                float(np.any(np.abs(np.nan_to_num(hc_vec)) > 1e-8)),
            ],
            dtype=np.float32,
        )

        # Prepare tensors
        imu_t = torch.from_numpy(imu).float().unsqueeze(0).to(self.device)
        ppg_t = torch.from_numpy(ppg).float().unsqueeze(0).to(self.device)
        vitals_t = torch.from_numpy(vitals).float().unsqueeze(0).to(self.device)
        hc_t = torch.from_numpy(np.nan_to_num(hc_vec, nan=0.0).astype(np.float32)).unsqueeze(0).to(self.device)
        mask_t = torch.from_numpy(modality_mask).unsqueeze(0).to(self.device)

        # Forward
        outputs = self.model({
            "imu": imu_t,
            "ppg": ppg_t,
            "vitals": vitals_t,
            "handcrafted_features": hc_t,
            "modality_mask": mask_t,
        })

        # Extract probabilities
        raw = {
            "fall_prob": float(torch.sigmoid(outputs["fall_logit"]).item()),
            "instability_prob": float(torch.sigmoid(outputs["instability_logit"]).item()),
            "quality_score": float(torch.sigmoid(outputs["quality_logit"]).item()),
            "risk_score": float(outputs["risk_score"].item()),
        }

        if smooth:
            for key in self._ema_state:
                self._ema_state[key] = (
                    self.ema_alpha * raw[key]
                    + (1 - self.ema_alpha) * self._ema_state[key]
                )
            return self._ema_state.copy()

        return raw

    def reset(self):
        """Reset EMA state for a new session."""
        self._ema_state = {
            "fall_prob": 0.0,
            "instability_prob": 0.0,
            "quality_score": 1.0,
            "risk_score": 0.0,
        }

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str,
        device: str = "cpu",
        ema_alpha: float = 0.3,
    ) -> "HealthAlertPredictor":
        """Create predictor from saved checkpoint."""
        from src.models.multitask_model_v2 import HealthAlertModelV2
        from src.utils.io import load_checkpoint

        dev = torch.device(device)
        ckpt = load_checkpoint(checkpoint_path, device=device)

        model = HealthAlertModelV2()
        model.load_state_dict(ckpt["model_state_dict"])
        model.to(dev)

        logger.info(f"Loaded model from {checkpoint_path}")
        return cls(model, dev, ema_alpha)
