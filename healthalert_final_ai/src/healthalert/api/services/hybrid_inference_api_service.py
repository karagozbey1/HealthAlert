from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from src.healthalert.api.schemas.hybrid_inference_schema import (
    ActivityExpertBlock,
    ExpertsBlock,
    FallExpertBlock,
    GaitExpertBlock,
    HybridInferenceRequest,
    HybridInferenceResponse,
    MissingModalitiesBlock,
    PersonalizationBlock,
    PPGQualityBlock,
    RiskBlock,
    RuntimeExpertBlock,
    UIBlock,
)
from src.healthalert.inference.hybrid_inference_service import HybridInferenceService


UI_MAPPING = {
    "normal": {
        "title": "Durum normal",
        "message": "Durum normal gorunuyor.",
        "color_level": "green",
        "show_alert": False,
        "ask_user_confirmation": False,
    },
    "caution": {
        "title": "Dikkat",
        "message": "Dikkat gerektiren hafif risk sinyalleri var.",
        "color_level": "yellow",
        "show_alert": False,
        "ask_user_confirmation": False,
    },
    "high_risk": {
        "title": "Risk yuksek",
        "message": "Risk seviyesi yukseldi. Kullanicidan durum onayi istenmeli.",
        "color_level": "orange",
        "show_alert": True,
        "ask_user_confirmation": True,
    },
    "critical": {
        "title": "Kritik risk",
        "message": "Kritik risk algilandi. Alarm ve bildirim akisi tetiklenmeli.",
        "color_level": "red",
        "show_alert": True,
        "ask_user_confirmation": True,
    },
}


class HybridInferenceAPIService:
    def __init__(self, config_path: str = "config/hybrid_runtime_config.yaml") -> None:
        self.config_path = config_path
        self.runtime_service = HybridInferenceService(
            config_path=config_path,
            device="cpu",
            enable_temporal_smoothing=True,
        )

    @staticmethod
    def _to_imu(value: List[List[float]] | None) -> np.ndarray | None:
        if value is None:
            return None
        return np.asarray(value, dtype=np.float32)

    @staticmethod
    def _to_ppg(value: Any) -> np.ndarray | None:
        if value is None:
            return None
        arr = np.asarray(value, dtype=np.float32)
        return arr.squeeze()

    @staticmethod
    def _extract_reason_subset(reasons: List[str], prefixes: tuple[str, ...]) -> List[str]:
        return [r for r in reasons if r.startswith(prefixes)]

    def infer(self, request: HybridInferenceRequest) -> HybridInferenceResponse:
        imu = self._to_imu(request.imu_window)
        ppg = self._to_ppg(request.ppg_window)
        vitals = None
        if request.heart_rate is not None or request.spo2 is not None:
            vitals = {"hr": request.heart_rate, "spo2": request.spo2}

        runtime = self.runtime_service.infer(
            imu_window=imu,
            ppg_window=ppg,
            vitals_values=vitals,
            user_id=request.patient_id,
            user_confirmed_okay=request.user_confirmed_okay,
            baseline_override=request.user_baseline,
        )

        cfg = self.runtime_service.config
        risk_level = runtime["risk_level"]
        ui = UI_MAPPING[risk_level]
        reasons = runtime.get("reasons", []) or ["no_strong_risk_signals"]

        missing = MissingModalitiesBlock(
            imu_missing=imu is None,
            ppg_missing=ppg is None,
            baseline_missing=bool(runtime.get("cold_start_mode", True)),
        )

        vitals_reasons = self._extract_reason_subset(
            reasons,
            ("ppg_", "hr_", "spo2_", "vitals_", "baseline_missing"),
        )
        gait_reasons = self._extract_reason_subset(
            reasons,
            ("runtime_motion_", "motion_", "post_impact_", "imu_missing"),
        )

        return HybridInferenceResponse(
            patient_id=request.patient_id,
            timestamp=request.timestamp,
            data_mode=request.data_mode,
            risk=RiskBlock(
                final_risk_score=float(runtime["final_risk_score"]),
                risk_level=risk_level,
                confidence_score=float(runtime["confidence_score"]),
                recommended_action=str(runtime["recommended_action"]),
                reasons=reasons,
            ),
            experts=ExpertsBlock(
                fall=FallExpertBlock(
                    enabled=bool(cfg["fall_expert"]["enabled"]),
                    fall_probability=float(runtime["fall_probability"]),
                    threshold_caution=float(cfg["fall_expert"]["threshold_caution"]),
                    threshold_balanced=float(cfg["fall_expert"]["threshold_balanced"]),
                ),
                activity=ActivityExpertBlock(
                    enabled=bool(cfg["activity_expert"]["enabled"]),
                    status=str(cfg["activity_expert"]["status"]),
                    activity_context=str(runtime["activity_context"]),
                    confidence=float(runtime.get("activity_confidence", 0.0)),
                ),
                ppg_quality=PPGQualityBlock(
                    enabled=bool(cfg["ppg_quality_expert"]["enabled"]),
                    quality_label=str(runtime["ppg_quality_label"]),
                    quality_score=runtime.get("ppg_quality_score"),
                ),
                vitals=RuntimeExpertBlock(
                    ml_enabled=False,
                    mode=str(cfg["vitals_context_model"]["mode"]),
                    contribution=float(runtime["vitals_contribution"]),
                    reasons=vitals_reasons,
                ),
                gait=GaitExpertBlock(
                    ml_enabled=bool(cfg["gait_instability_model"]["enabled"]),
                    mode=str(cfg["gait_instability_model"]["mode"]),
                    contribution=float(runtime["gait_contribution"]),
                    reasons=gait_reasons,
                    gait_abnormal_probability=float(runtime.get("gait_abnormal_probability", 0.0)),
                ),
            ),
            personalization=PersonalizationBlock(
                baseline_available=not bool(runtime.get("cold_start_mode", True)),
                cold_start_mode=bool(runtime.get("cold_start_mode", True)),
                personalization_adjustment=float(runtime["personalization_adjustment"]),
                baseline_update_allowed=bool(runtime.get("baseline_update_allowed", False)),
            ),
            missing_modalities=missing,
            ui=UIBlock(**ui),
        )
