from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HybridInferenceRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    timestamp: str
    data_mode: Literal["live", "demo", "npz_demo"] = "live"
    imu_window: Optional[List[List[float]]] = None
    ppg_window: Optional[List[float] | List[List[float]]] = None
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    user_baseline: Optional[Dict[str, Any]] = None
    user_confirmed_okay: bool = False

    @field_validator("imu_window")
    @classmethod
    def validate_imu_window(cls, value: Optional[List[List[float]]]) -> Optional[List[List[float]]]:
        if value is None:
            return value
        if not value or not isinstance(value[0], list):
            raise ValueError("imu_window must be a 2D array")
        return value


class RiskBlock(BaseModel):
    final_risk_score: float
    risk_level: Literal["normal", "caution", "high_risk", "critical"]
    confidence_score: float
    recommended_action: str
    reasons: List[str]


class FallExpertBlock(BaseModel):
    enabled: bool
    fall_probability: float
    threshold_caution: float
    threshold_balanced: float


class ActivityExpertBlock(BaseModel):
    enabled: bool
    status: str
    activity_context: str
    confidence: float


class PPGQualityBlock(BaseModel):
    enabled: bool
    quality_label: str
    quality_score: Optional[float]


class RuntimeExpertBlock(BaseModel):
    ml_enabled: bool
    mode: str
    contribution: float
    reasons: List[str]


class GaitExpertBlock(RuntimeExpertBlock):
    gait_abnormal_probability: float


class ExpertsBlock(BaseModel):
    fall: FallExpertBlock
    activity: ActivityExpertBlock
    ppg_quality: PPGQualityBlock
    vitals: RuntimeExpertBlock
    gait: GaitExpertBlock


class PersonalizationBlock(BaseModel):
    baseline_available: bool
    cold_start_mode: bool
    personalization_adjustment: float
    baseline_update_allowed: bool


class MissingModalitiesBlock(BaseModel):
    imu_missing: bool
    ppg_missing: bool
    baseline_missing: bool


class UIBlock(BaseModel):
    title: str
    message: str
    color_level: Literal["green", "yellow", "orange", "red"]
    show_alert: bool
    ask_user_confirmation: bool


class HybridInferenceResponse(BaseModel):
    patient_id: str
    timestamp: str
    data_mode: Literal["live", "demo", "npz_demo"]
    risk: RiskBlock
    experts: ExpertsBlock
    personalization: PersonalizationBlock
    missing_modalities: MissingModalitiesBlock
    ui: UIBlock
