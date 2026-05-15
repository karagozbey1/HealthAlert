from __future__ import annotations

import json
import logging
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch
import yaml

from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
from src.healthalert.fusion.runtime_gait_rules import compute_runtime_gait_motion_score
from src.healthalert.fusion.runtime_vitals_rules import compute_runtime_vitals_adjustment
from src.healthalert.fusion.temporal_risk_smoother import TemporalRiskSmoother
from src.healthalert.models.activity_expert import ACTIVITY_CLASSES, build_activity_expert
from src.healthalert.models.fall_expert import build_fall_expert
from src.healthalert.models.gait_instability_expert import build_gait_instability_expert
from src.healthalert.models.ppg_quality_expert import PPG_QUALITY_CLASSES, build_ppg_quality_expert
from src.healthalert.personalization.baseline_storage_schema import UserBaselineProfile
from src.healthalert.personalization.user_baseline import UserBaselineEngine

log = logging.getLogger(__name__)

REJECTED_MODEL_PATH_MARKERS = (
    "activity_expert/best_model.pt",
    "activity_expert_balanced",
    "activity_expert_v2/best_model.pt",
    "gait_instability_v2_2_ablation",
    "gait_instability_expert/best_model.pt",
    "vitals_context_expert",
)


class HybridInferenceService:
    def __init__(
        self,
        *,
        config_path: str = "config/hybrid_runtime_config.yaml",
        device: str = "auto",
        enable_temporal_smoothing: bool = True,
        baselines_dir: str = "outputs/hybrid_redesign/personalization/baselines",
    ) -> None:
        self.device = torch.device("cuda" if (device == "auto" and torch.cuda.is_available()) else "cpu")
        if device != "auto":
            self.device = torch.device(device)

        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent.parent
        self.config = self._load_config(self.config_path)
        self._validate_runtime_config()
        self.enable_temporal_smoothing = enable_temporal_smoothing
        self.baselines_dir = self._resolve_path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

        self._fall = None
        self._activity = None
        self._ppgq = None
        self._gait = None
        self._norm_stats: Dict[str, Optional[Dict[str, Any]]] = {}
        self.loaded_model_paths: list[str] = []
        self._baseline_engines: Dict[str, UserBaselineEngine] = {}
        self._smoothers: Dict[str, TemporalRiskSmoother] = {}
        self._fusion = RiskFusionEngine(
            fall_threshold_caution=float(self.config["fall_expert"]["threshold_caution"]),
            fall_threshold_balanced=float(self.config["fall_expert"]["threshold_balanced"]),
            gait_max_contribution_points=float(
                self.config["gait_instability_model"].get("max_contribution_points", 5)
            ),
        )

    def _load_config(self, p: str | Path) -> Dict[str, Any]:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _validate_runtime_config(self) -> None:
        rejected = self.config.get("rejected_models", {})
        enabled_rejected = [name for name, cfg in rejected.items() if bool(cfg.get("enabled", False))]
        if enabled_rejected:
            raise ValueError(f"Rejected models cannot be enabled: {enabled_rejected}")

        enabled_model_paths = []
        for key in (
            "fall_expert",
            "ppg_quality_expert",
            "activity_expert",
            "gait_instability_model",
        ):
            block = self.config.get(key, {})
            if bool(block.get("enabled", False)) and block.get("model_path"):
                enabled_model_paths.append(str(block["model_path"]).replace("\\", "/"))

        for model_path in enabled_model_paths:
            for marker in REJECTED_MODEL_PATH_MARKERS:
                if marker in model_path:
                    raise ValueError(f"Rejected model path configured for runtime load: {model_path}")

        activity_path = str(self.config["activity_expert"]["model_path"]).replace("\\", "/")
        accepted_activity_markers = (
            "activity_expert_v2_uci_only",
            "activity_v2_pamap2_repair/exp_a_uci_only_baseline",
        )
        if not any(marker in activity_path for marker in accepted_activity_markers):
            raise ValueError(f"Activity runtime model is not the accepted UCI-only artifact: {activity_path}")

    def _resolve_path(self, path_value: str | Path) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path

    @staticmethod
    def _record_path(model_path: str) -> str:
        return str(model_path).replace("\\", "/")

    def _load_checkpoint_state(self, model_path: str) -> Optional[Dict[str, Any]]:
        ckpt = self._resolve_path(model_path)
        if not ckpt.exists():
            log.warning("Checkpoint not found: %s", ckpt)
            return None
        state = torch.load(ckpt, map_location=self.device)
        self.loaded_model_paths.append(self._record_path(model_path))
        if isinstance(state, dict) and "model_state_dict" in state:
            state = state["model_state_dict"]
        if not isinstance(state, dict):
            log.warning("Unexpected checkpoint format: %s", ckpt)
            return None
        return state

    def _build_model_from_state(
        self,
        builder,
        state: Dict[str, Any],
        build_cfg: Optional[Dict[str, Any]] = None,
    ):
        m = builder(build_cfg or {}).to(self.device)
        m.load_state_dict(state, strict=False)
        m.eval()
        return m

    def _load_model(self, builder, model_path: str, build_cfg: Optional[Dict[str, Any]] = None):
        state = self._load_checkpoint_state(model_path)
        if state is None:
            return None
        return self._build_model_from_state(builder, state, build_cfg=build_cfg)

    def _load_norm_stats(self, component_key: str) -> Optional[Dict[str, Any]]:
        if component_key in self._norm_stats:
            return self._norm_stats[component_key]
        path_value = self.config.get(component_key, {}).get("norm_stats_path")
        if not path_value:
            self._norm_stats[component_key] = None
            return None
        path = self._resolve_path(path_value)
        if not path.exists():
            log.warning("Norm stats not found: %s", path)
            self._norm_stats[component_key] = None
            return None
        with open(path, "r", encoding="utf-8") as f:
            self._norm_stats[component_key] = json.load(f)
        return self._norm_stats[component_key]

    def _apply_channel_norm(self, arr: np.ndarray, component_key: str) -> np.ndarray:
        stats = self._load_norm_stats(component_key)
        if not stats:
            return arr

        mean = np.asarray(stats.get("mean_per_channel", []), dtype=np.float32)
        std = np.asarray(stats.get("std_per_channel", []), dtype=np.float32)
        if mean.size == 0 or std.size == 0:
            return arr
        std = np.where(std <= 1e-6, 1.0, std)

        x = np.asarray(arr, dtype=np.float32).copy()
        clip_value = stats.get("clip_g")
        if clip_value is not None:
            x = np.clip(x, -float(clip_value), float(clip_value))

        if x.ndim == 1 and mean.size == 1:
            return (x - mean[0]) / std[0]
        if x.ndim == 2 and x.shape[0] == mean.size:
            return (x - mean[:, np.newaxis]) / std[:, np.newaxis]
        return x

    @staticmethod
    def _infer_num_classes_from_state(state: Dict[str, Any], key: str) -> Optional[int]:
        w = state.get(key)
        if w is None:
            return None
        if hasattr(w, "shape") and len(w.shape) >= 1:
            return int(w.shape[0])
        return None

    def _get_baseline_engine(self, user_id: str) -> UserBaselineEngine:
        if user_id in self._baseline_engines:
            return self._baseline_engines[user_id]
        e = UserBaselineEngine(user_id=user_id)
        p = self.baselines_dir / f"{user_id}_baseline.json"
        if p.exists():
            e.load(str(p))
        self._baseline_engines[user_id] = e
        return e

    def _get_smoother(self, user_id: str) -> TemporalRiskSmoother:
        if user_id not in self._smoothers:
            self._smoothers[user_id] = TemporalRiskSmoother()
        return self._smoothers[user_id]

    @staticmethod
    def _prep_imu(imu_window: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if imu_window is None:
            return None
        arr = np.asarray(imu_window, dtype=np.float32)
        if arr.ndim != 2:
            return None
        if arr.shape[0] != 6 and arr.shape[1] == 6:
            arr = arr.T
        if arr.shape[0] != 6:
            return None
        return arr

    @staticmethod
    def _prep_ppg(ppg_window: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if ppg_window is None:
            return None
        arr = np.asarray(ppg_window, dtype=np.float32).squeeze()
        if arr.ndim != 1:
            return None
        return arr

    def _run_fall(self, imu: Optional[np.ndarray]) -> float:
        if imu is None or not self.config["fall_expert"]["enabled"]:
            return 0.0
        if self._fall is None:
            self._fall = self._load_model(build_fall_expert, self.config["fall_expert"]["model_path"])
        if self._fall is None:
            return 0.0
        imu_norm = self._apply_channel_norm(imu, "fall_expert")
        x = torch.tensor(imu_norm[np.newaxis, ...], dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = self._fall(x)
        return float(out["fall_prob"].squeeze().cpu().item())

    def _run_activity(self, imu: Optional[np.ndarray]) -> Dict[str, Any]:
        if imu is None or not self.config["activity_expert"]["enabled"]:
            return {"activity_context": "unknown", "confidence": 0.0}
        if self._activity is None:
            state = self._load_checkpoint_state(self.config["activity_expert"]["model_path"])
            if state is not None:
                ncls = self._infer_num_classes_from_state(state, "classifier.3.weight")
                cfg = {"num_classes": ncls} if ncls is not None else {}
                self._activity = self._build_model_from_state(
                    build_activity_expert,
                    state,
                    build_cfg=cfg,
                )
        if self._activity is None:
            return {"activity_context": "unknown", "confidence": 0.0}
        imu_norm = self._apply_channel_norm(imu, "activity_expert")
        x = torch.tensor(imu_norm[np.newaxis, ...], dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = self._activity(x)
        cls_idx = int(out["predicted_class"].squeeze().cpu().item())
        probs = out["activity_probs"].squeeze().cpu().numpy()
        label = ACTIVITY_CLASSES[cls_idx] if 0 <= cls_idx < len(ACTIVITY_CLASSES) else "unknown"
        confidence = float(probs[cls_idx]) if probs.ndim == 1 and 0 <= cls_idx < len(probs) else 0.0
        return {"activity_context": label, "confidence": confidence}

    def _run_ppg_quality(self, ppg: Optional[np.ndarray]) -> Dict[str, Any]:
        if ppg is None or not self.config["ppg_quality_expert"]["enabled"]:
            return {"score": None, "label": "missing"}
        if self._ppgq is None:
            state = self._load_checkpoint_state(self.config["ppg_quality_expert"]["model_path"])
            if state is not None:
                ncls = self._infer_num_classes_from_state(state, "classifier.3.weight")
                cfg = {"num_classes": ncls} if ncls is not None else {}
                self._ppgq = self._build_model_from_state(
                    build_ppg_quality_expert,
                    state,
                    build_cfg=cfg,
                )
        if self._ppgq is None:
            return {"score": None, "label": "missing"}
        ppg_norm = self._apply_channel_norm(ppg, "ppg_quality_expert")
        x = torch.tensor(ppg_norm[np.newaxis, np.newaxis, :], dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = self._ppgq(x)
        probs = out["quality_probs"].squeeze().cpu().numpy()
        idx = int(np.argmax(probs))
        if len(probs) == 2:
            label = ["good_quality", "bad_quality"][idx]
        else:
            label = PPG_QUALITY_CLASSES[idx] if idx < len(PPG_QUALITY_CLASSES) else "unknown"
        return {"score": float(probs[0]), "label": label}

    def _run_gait(self, imu: Optional[np.ndarray]) -> Dict[str, Any]:
        if imu is None or not self.config["gait_instability_model"]["enabled"]:
            return {"score": 0.0, "label": "missing"}
        if self._gait is None:
            self._gait = self._load_model(
                build_gait_instability_expert,
                self.config["gait_instability_model"]["model_path"],
            )
        if self._gait is None:
            return {"score": 0.0, "label": "missing"}
        imu_norm = self._apply_channel_norm(imu, "gait_instability_model")
        x = torch.tensor(imu_norm[np.newaxis, ...], dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = self._gait(x)
        score = float(out["gait_instability_score"].squeeze().cpu().item())
        threshold = float(self.config["gait_instability_model"].get("threshold", 0.10))
        return {
            "score": max(0.0, min(1.0, score)),
            "label": "abnormal" if score >= threshold else "stable",
        }

    def _disabled_models(self) -> list[str]:
        disabled = [
            name
            for name, block in self.config.get("rejected_models", {}).items()
            if not bool(block.get("enabled", False))
        ]
        if not bool(self.config.get("vitals_context_model", {}).get("enabled", False)):
            disabled.append("vitals_context_model")
        if not bool(self.config.get("tremor_context", {}).get("enabled", False)):
            disabled.append("tremor_context")
        return list(dict.fromkeys(disabled))

    def infer(
        self,
        *,
        imu_window: Optional[np.ndarray],
        ppg_window: Optional[np.ndarray],
        vitals_values: Optional[Dict[str, float]] = None,
        user_id: str = "anonymous",
        user_confirmed_okay: bool = False,
        baseline_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        imu = self._prep_imu(imu_window)
        ppg = self._prep_ppg(ppg_window)

        fall_probability = self._run_fall(imu)
        activity_out = self._run_activity(imu)
        activity_context = activity_out["activity_context"]
        ppg_quality = self._run_ppg_quality(ppg)

        gait_rt = compute_runtime_gait_motion_score(imu)
        gait_features = gait_rt.get("features", {})
        gait_ml = self._run_gait(imu)
        gait_score = float(gait_ml["score"])

        baseline_engine = self._get_baseline_engine(user_id)
        if baseline_override:
            allowed = {f.name for f in fields(UserBaselineProfile)}
            merged = baseline_engine.profile.to_dict()
            for key, value in baseline_override.items():
                if key in allowed:
                    merged[key] = value
            baseline_engine.profile = UserBaselineProfile(**merged)
        baseline_missing = not baseline_engine.profile.is_calibrated()
        baseline_dict = baseline_engine.profile.to_dict() if not baseline_missing else None

        vitals_rt = compute_runtime_vitals_adjustment(
            ppg_quality_label=ppg_quality["label"],
            ppg_quality_score=ppg_quality["score"],
            vitals=vitals_values,
            baseline=baseline_dict,
        )

        observation = {
            "heart_rate": None if vitals_values is None else vitals_values.get("hr"),
            "spo2": None if vitals_values is None else vitals_values.get("spo2"),
            "gait_instability_score": gait_score,
            "motion_intensity": gait_features.get("motion_intensity"),
            "activity_class": activity_context,
        }
        dev = baseline_engine.compute_deviation(observation)
        personalization_adjustment = float(dev["personal_deviation_score"]) * 10.0

        signal_confidence = 1.0
        if imu is None:
            signal_confidence -= 0.5
        if ppg is None:
            signal_confidence -= 0.2
        signal_confidence = max(0.2, signal_confidence)

        missing_flags = {
            "imu_missing": imu is None,
            "ppg_missing": ppg is None,
            "baseline_missing": baseline_missing,
            "post_impact_low_motion": bool(gait_features.get("post_impact_low_motion", False)),
        }

        fused = self._fusion.fuse(
            fall_probability=fall_probability,
            activity_context=activity_context,
            ppg_quality_score=ppg_quality["score"],
            ppg_quality_label=ppg_quality["label"],
            runtime_vitals_adjustment=float(vitals_rt["adjustment"]),
            runtime_gait_motion_score=gait_score,
            personalization_adjustment=personalization_adjustment,
            signal_confidence=signal_confidence,
            missing_modality_flags=missing_flags,
        )

        fused["reasons"] = list(
            dict.fromkeys(
                fused.get("reasons", [])
                + gait_rt.get("reasons", [])
                + vitals_rt.get("reasons", [])
                + dev.get("reasons", [])
            )
        )

        if self.enable_temporal_smoothing:
            smoother = self._get_smoother(user_id)
            fused = smoother.update(fused, user_confirmed_okay=user_confirmed_okay)

        baseline_update_allowed = baseline_engine.should_update(
            final_risk_score=float(fused["final_risk_score"]),
            fall_probability=fall_probability,
            ppg_quality_score=ppg_quality["score"],
            risk_level=fused["risk_level"],
            signal_confidence=signal_confidence,
        )
        if baseline_update_allowed:
            baseline_engine.update(observation, ppg_quality_score=ppg_quality["score"])

        fused["runtime_vitals_adjustment"] = round(float(vitals_rt["adjustment"]), 3)
        fused["runtime_gait_motion_score"] = round(float(gait_score), 4)
        fused["gait_abnormal_probability"] = round(float(gait_score), 4)
        fused["gait_quality_label"] = gait_ml["label"]
        fused["ppg_quality_score"] = (
            None if ppg_quality["score"] is None else round(float(ppg_quality["score"]), 4)
        )
        fused["ppg_quality_label"] = ppg_quality["label"]
        fused["activity_context"] = activity_context
        fused["activity_confidence"] = round(float(activity_out["confidence"]), 4)
        fused["personalization_adjustment"] = round(float(fused["personalization_adjustment"]), 3)
        fused["baseline_update_allowed"] = baseline_update_allowed
        fused["cold_start_mode"] = baseline_missing
        fused["disabled_models"] = self._disabled_models()
        return fused

    def save_user_baseline(self, user_id: str) -> Optional[str]:
        engine = self._baseline_engines.get(user_id)
        if engine is None:
            return None
        out = self.baselines_dir / f"{user_id}_baseline.json"
        engine.save(str(out))
        return str(out)
