"""Prototype inference predictor for HealthAlert.

Loads the trained best_model.pt and produces:
- Per-task class probabilities
- ml_risk_score (0-100)
- risk_level: normal / caution / high_risk / critical
- Graceful fallback when modality is absent
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

from src.models.prototype_model import PrototypeHealthAlertModel

logger = logging.getLogger("healthalert.inference.prototype_predictor")


# ── Label mappings (mirrored from prototype_training.yaml) ────────────────

_DEFAULT_CLASS_NAMES: Dict[str, List[str]] = {
    "fall_detection":   ["normal", "fall", "near_fall"],
    "ppg_quality":      ["bad_quality", "good_quality"],
    "vitals_context":   ["rest", "active", "poor_signal"],
    "activity_context": ["normal", "fall", "near_fall", "instability",
                         "walking", "sitting", "standing", "lying"],
    "gait_instability": ["normal_gait", "suspect_gait"],
}

_DEFAULT_LABEL_MAPS: Dict[str, Dict[int, int]] = {
    "fall_detection":   {0: 0, 1: 1, 2: 2, 99: -1},
    "ppg_quality":      {0: 1, 10: 1, 11: 1, 20: 1, 21: 0, 99: -1},
    "vitals_context":   {0: 0, 11: 0, 20: 0, 10: 1, 21: 2, 99: -1},
    "activity_context": {0: 0, 1: 1, 2: 2, 3: 3, 10: 4, 11: 5, 12: 6, 13: 7, 99: -1},
    "gait_instability": {0: 0, 99: 1},
}

# Risk level boundaries (0-1 raw score → label)
_RISK_LEVELS = [
    (0.75, "critical"),
    (0.55, "high_risk"),
    (0.30, "caution"),
    (0.0,  "normal"),
]


# ── Risk score fusion ─────────────────────────────────────────────────────

class RiskScoreFusion:
    """Fuse task probabilities into a single ml_risk_score in [0, 100].

    fusion_weights match prototype_training.yaml inference section:
      fall_prob_weight:           0.45
      near_fall_prob_weight:      0.25
      gait_instability_weight:    0.20
      ppg_quality_penalty_weight: 0.10
    """

    def __init__(
        self,
        fall_prob_weight: float = 0.45,
        near_fall_prob_weight: float = 0.25,
        gait_instability_weight: float = 0.20,
        ppg_quality_penalty_weight: float = 0.10,
    ) -> None:
        self.w_fall = fall_prob_weight
        self.w_near = near_fall_prob_weight
        self.w_gait = gait_instability_weight
        self.w_ppg = ppg_quality_penalty_weight

    def compute(self, task_probs: Dict[str, List[float]]) -> Tuple[float, str]:
        """
        Parameters
        ----------
        task_probs:
            Dict of task_name → list of class probabilities.
            Keys expected: fall_detection, gait_instability, ppg_quality.

        Returns
        -------
        (ml_risk_score_0_100, risk_level_string)
        """
        # Fall detection: P(fall) and P(near_fall)
        fall_probs = task_probs.get("fall_detection", [1.0, 0.0, 0.0])
        p_fall = fall_probs[1] if len(fall_probs) > 1 else 0.0
        p_near = fall_probs[2] if len(fall_probs) > 2 else 0.0

        # Gait instability: P(suspect_gait)
        gait_probs = task_probs.get("gait_instability", [1.0, 0.0])
        p_gait = gait_probs[1] if len(gait_probs) > 1 else 0.0

        # PPG quality: P(bad_quality) → penalty signal
        ppg_probs = task_probs.get("ppg_quality", [0.0, 1.0])
        p_bad_ppg = ppg_probs[0] if len(ppg_probs) > 0 else 0.0

        raw_score = (
            self.w_fall  * p_fall
            + self.w_near * p_near
            + self.w_gait * p_gait
            + self.w_ppg  * p_bad_ppg
        )

        # Clamp to [0, 1] and scale to 0-100
        raw_score = float(np.clip(raw_score, 0.0, 1.0))
        ml_risk_score = round(raw_score * 100.0, 2)

        # Risk level
        risk_level = "normal"
        for threshold, level in _RISK_LEVELS:
            if raw_score >= threshold:
                risk_level = level
                break

        return ml_risk_score, risk_level


# ── Prototype predictor ───────────────────────────────────────────────────

class PrototypePredictor:
    """Load trained model and run inference on 4-second sensor windows.

    Parameters
    ----------
    model_path:
        Path to best_model.pt checkpoint.
    label_mappings_path:
        Optional path to label_mappings.json (auto-detected if None).
    device:
        'cpu', 'cuda', or 'auto'.
    fall_threshold:
        Decision threshold for fall class probability.  Use 0.4 for
        conservative (demo-safe) behaviour.
    """

    def __init__(
        self,
        model_path: str | Path,
        label_mappings_path: Optional[str | Path] = None,
        device: str = "auto",
        fall_threshold: float = 0.4,
    ) -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model checkpoint not found: {model_path}")

        if device == "auto":
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self._device = torch.device(device)

        self.fall_threshold = fall_threshold

        # Load model
        ckpt = torch.load(model_path, map_location=self._device)
        self.model = PrototypeHealthAlertModel()
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.model.to(self._device)
        self.model.eval()

        logger.info(
            f"Loaded model from {model_path} "
            f"(epoch={ckpt.get('epoch', '?')}, "
            f"best_score={ckpt.get('best_val_score', 'N/A')})"
        )

        # Load label mappings
        if label_mappings_path is None:
            candidate = model_path.parent / "label_mappings.json"
            if candidate.exists():
                label_mappings_path = candidate

        if label_mappings_path and Path(label_mappings_path).exists():
            with open(label_mappings_path, "r") as f:
                raw = json.load(f)
            self.class_names: Dict[str, List[str]] = {
                t: v.get("class_names", _DEFAULT_CLASS_NAMES.get(t, []))
                for t, v in raw.items()
            }
        else:
            self.class_names = dict(_DEFAULT_CLASS_NAMES)
            logger.warning(
                "label_mappings.json not found — using default class names."
            )

        self.risk_fusion = RiskScoreFusion()

    # ── Core predict ──────────────────────────────────────────────────────

    def predict(
        self,
        imu: Optional[np.ndarray] = None,
        ppg: Optional[np.ndarray] = None,
        vitals: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Run inference on a single 4-second window.

        Parameters
        ----------
        imu:
            (200, 6) float32 array (accel_xyz + gyro_xyz).  Pass None or
            zeros to signal absent IMU modality.
        ppg:
            (200, 1) float32 array.  Pass None or zeros to signal absent PPG.
        vitals:
            Optional dict with keys 'hr_bpm', 'spo2_pct' for additional
            post-processing context.

        Returns
        -------
        dict with keys:
          task_probs      — per-task class probabilities
          task_labels     — predicted class names
          ml_risk_score   — 0-100 float
          risk_level      — normal / caution / high_risk / critical
          fall_detected   — bool (using fall_threshold)
          confidence      — dict of per-task max-probability (model confidence)
          modality_flags  — dict showing which modalities were present
          vitals_warning  — bool if HR/SpO2 out of safe range
          inference_ms    — latency in milliseconds
        """
        # ── Prepare inputs ────────────────────────────────────────────────
        imu_arr = np.zeros((200, 6), dtype=np.float32) if imu is None else np.asarray(imu, dtype=np.float32)
        ppg_arr = np.zeros((200, 1), dtype=np.float32) if ppg is None else np.asarray(ppg, dtype=np.float32)

        has_imu = bool(imu_arr.sum() != 0.0)
        has_ppg = bool(ppg_arr.sum() != 0.0)

        imu_t = torch.tensor(imu_arr, dtype=torch.float32).unsqueeze(0).to(self._device)  # (1,200,6)
        ppg_t = torch.tensor(ppg_arr, dtype=torch.float32).unsqueeze(0).to(self._device)  # (1,200,1)

        batch = {"imu": imu_t, "ppg": ppg_t}

        # ── Inference ─────────────────────────────────────────────────────
        t0 = time.perf_counter()
        with torch.no_grad():
            logits_dict = self.model(batch)
        inference_ms = (time.perf_counter() - t0) * 1000.0

        # ── Convert to probabilities ──────────────────────────────────────
        task_probs: Dict[str, List[float]] = {}
        task_labels: Dict[str, str] = {}
        confidence: Dict[str, float] = {}

        for task, logits in logits_dict.items():
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()

            # Degrade confidence if relevant modality is absent
            if task in ("ppg_quality", "vitals_context") and not has_ppg:
                # PPG-based tasks: output is unreliable — report low confidence
                probs = np.ones_like(probs) / len(probs)  # uniform
                logger.debug(f"[{task}] PPG absent — uniform probability returned.")

            if task in ("fall_detection", "gait_instability") and not has_imu:
                probs = np.ones_like(probs) / len(probs)
                logger.debug(f"[{task}] IMU absent — uniform probability returned.")

            probs_list = probs.tolist()
            task_probs[task] = probs_list

            pred_idx = int(np.argmax(probs))
            names = self.class_names.get(task, [str(i) for i in range(len(probs))])
            task_labels[task] = names[pred_idx] if pred_idx < len(names) else str(pred_idx)
            confidence[task] = float(probs[pred_idx])

        # ── Fall decision (threshold-based) ──────────────────────────────
        fall_probs = task_probs.get("fall_detection", [1.0, 0.0, 0.0])
        p_fall = fall_probs[1] if len(fall_probs) > 1 else 0.0
        fall_detected = bool(p_fall >= self.fall_threshold)

        # ── Risk score ────────────────────────────────────────────────────
        ml_risk_score, risk_level = self.risk_fusion.compute(task_probs)

        # ── Vitals warning ─────────────────────────────────────────────────
        vitals_warning = False
        if vitals:
            hr = vitals.get("hr_bpm", 70.0)
            spo2 = vitals.get("spo2_pct", 98.0)
            vitals_warning = bool(hr < 50 or hr > 130 or spo2 < 92)
            if vitals_warning:
                # Bump risk score slightly for abnormal vitals
                ml_risk_score = min(ml_risk_score + 10.0, 100.0)
                if ml_risk_score > 75.0:
                    risk_level = "critical"
                elif ml_risk_score > 55.0:
                    risk_level = "high_risk"

        # ── Low-confidence PPG handling ───────────────────────────────────
        ppg_quality_probs = task_probs.get("ppg_quality", [0.0, 1.0])
        p_bad_ppg = ppg_quality_probs[0] if ppg_quality_probs else 0.0
        ppg_unreliable = bool(p_bad_ppg > 0.7)

        return {
            "task_probs":      task_probs,
            "task_labels":     task_labels,
            "ml_risk_score":   ml_risk_score,
            "risk_level":      risk_level,
            "fall_detected":   fall_detected,
            "fall_probability": round(p_fall, 4),
            "confidence":      confidence,
            "modality_flags":  {"has_imu": has_imu, "has_ppg": has_ppg},
            "vitals_warning":  vitals_warning,
            "ppg_unreliable":  ppg_unreliable,
            "inference_ms":    round(inference_ms, 3),
        }

    # ── Batch predict ─────────────────────────────────────────────────────

    def predict_batch(
        self,
        imu_batch: np.ndarray,
        ppg_batch: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """Run inference on a batch of windows.

        Parameters
        ----------
        imu_batch: (N, 200, 6)
        ppg_batch: (N, 200, 1)
        """
        results = []
        for i in range(len(imu_batch)):
            results.append(
                self.predict(
                    imu=imu_batch[i],
                    ppg=ppg_batch[i],
                )
            )
        return results

    # ── Utility ───────────────────────────────────────────────────────────

    @property
    def device(self) -> torch.device:
        return self._device

    def model_parameters(self) -> int:
        return self.model.count_parameters()
