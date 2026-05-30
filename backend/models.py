from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

# ORM kayitlari icin benzersiz kimlik uretir.
def _uuid() -> str:
    return str(uuid4())

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    birth_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LinkCode(Base):
    __tablename__ = "link_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    code_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    uses_remaining: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserRelation(Base):
    __tablename__ = "user_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    self_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    linked_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class LiveStatus(Base):
    __tablename__ = "live_statuses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    heart_rate: Mapped[float] = mapped_column(Float, default=72.0)
    spo2: Mapped[float] = mapped_column(Float, default=98.0)
    motion_score: Mapped[float] = mapped_column(Float, default=0.1)
    risk_score: Mapped[float] = mapped_column(Float, default=0.05)
    scenario: Mapped[str] = mapped_column(String(50), default="normal")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DevicePacketLog(Base):
    __tablename__ = "device_packet_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    packet_seq: Mapped[int] = mapped_column(Integer, nullable=False)

    accel_x: Mapped[float] = mapped_column(Float, default=0.0)
    accel_y: Mapped[float] = mapped_column(Float, default=0.0)
    accel_z: Mapped[float] = mapped_column(Float, default=0.0)
    gyro_x: Mapped[float] = mapped_column(Float, default=0.0)
    gyro_y: Mapped[float] = mapped_column(Float, default=0.0)
    gyro_z: Mapped[float] = mapped_column(Float, default=0.0)

    red_value: Mapped[int] = mapped_column(Integer, default=0)
    ir_value: Mapped[int] = mapped_column(Integer, default=0)
    heart_rate: Mapped[float] = mapped_column(Float, default=0.0)
    spo2: Mapped[float] = mapped_column(Float, default=0.0)
    signal_quality: Mapped[float] = mapped_column(Float, default=0.0)

    imu_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    ppg_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    hr_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    spo2_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    finger_detected: Mapped[bool] = mapped_column(Boolean, default=False)

    state_hint: Mapped[str] = mapped_column(String(50), default="normal")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DeviceRegistration(Base):
    __tablename__ = "device_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    summary: Mapped[str] = mapped_column(String(500))

class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(50), default="raised")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    countdown_total_sec: Mapped[int] = mapped_column(Integer, default=30)
    countdown_remaining_sec: Mapped[int] = mapped_column(Integer, default=30)
    recommendations: Mapped[str] = mapped_column(Text, default="[]")
    related_anomaly_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Saklanan onerileri liste olarak cozer.
    def get_recommendations(self) -> list[str]:
        try:
            return json.loads(self.recommendations)
        except Exception:
            return []

    # Oneri listesini JSON metni olarak saklar.
    def set_recommendations(self, items: list[str]) -> None:
        self.recommendations = json.dumps(items)

class PostEventSession(Base):
    __tablename__ = "post_event_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alert_events.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

class HistoryItem(Base):
    __tablename__ = "history_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(500))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    severity: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

class NotificationItem(Base):
    __tablename__ = "notification_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    sender_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(1000))
    notification_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doctor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AppSettings(Base):
    __tablename__ = "app_settings"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    battery_mode: Mapped[str] = mapped_column(String(20), default="balanced")
    background_monitoring: Mapped[bool] = mapped_column(Boolean, default=True)
    update_interval_seconds: Mapped[int] = mapped_column(Integer, default=4)
    alert_sensitivity: Mapped[str] = mapped_column(String(20), default="normal")

class SimulationState(Base):
    __tablename__ = "simulation_states"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    scenario_index: Mapped[int] = mapped_column(Integer, default=0)
    tick_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserBaseline(Base):
    __tablename__ = "user_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    hr_mean: Mapped[float] = mapped_column(Float, default=72.0)
    hr_std: Mapped[float] = mapped_column(Float, default=10.0)
    spo2_mean: Mapped[float] = mapped_column(Float, default=98.0)
    spo2_std: Mapped[float] = mapped_column(Float, default=1.5)
    motion_mean: Mapped[float] = mapped_column(Float, default=0.10)
    motion_std: Mapped[float] = mapped_column(Float, default=0.08)
    ppg_quality_mean: Mapped[float] = mapped_column(Float, default=0.85)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Ogrenme dongusu icin zaman penceresi oturumlarini saklar.
class LearningCaptureSession(Base):
    __tablename__ = "learning_capture_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # live | demo | replay | host_bridge
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="live")
    # normal | watch | warning | critical
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_sample_count: Mapped[int] = mapped_column(Integer, default=0)
    low_quality_sample_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    has_user_feedback: Mapped[bool] = mapped_column(Boolean, default=False)
    training_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    # raw | candidate | reviewed | approved | rejected | exported
    training_status: Mapped[str] = mapped_column(String(20), default="raw")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LearningWindow(Base):
    # Egitim icin tek bir zaman penceresi ornegini saklar.
    __tablename__ = "learning_windows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    window_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    # live | demo | replay | host_bridge
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="live")
    # normal | watch | warning | critical
    risk_level_at_capture: Mapped[str] = mapped_column(String(20), default="normal")
    final_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    baseline_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    ml_shadow_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieval_shadow_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistant_mode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # ok | not_ok | false_alarm | fall_confirmed | sensor_error | unknown
    user_feedback_label: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # normal | watch | warning | critical | fall_like | near_fall | sensor_error
    suggested_label: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    label_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    training_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserFeedbackEvent(Base):
    # Kullanici geri bildirimlerini ve bagli pencere bilgisini saklar.
    __tablename__ = "user_feedback_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    related_window_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    related_alert_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # ok | not_ok | false_alarm | fall_confirmed | sensor_error | other
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # mobile | relative | doctor | system
    feedback_source: Mapped[str] = mapped_column(String(20), nullable=False, default="mobile")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelVersionRegistry(Base):
    # Aktif model surumunu ve egitim kaynagini kayit altina alir.
    __tablename__ = "model_version_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_path: Mapped[str] = mapped_column(String(512), nullable=False)
    training_data_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # candidate | shadow | active | deprecated
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Kullaniciya ozel saglik profilini ve kisilestirme istatistiklerini saklar.
class PersonalHealthProfile(Base):
    __tablename__ = "personal_health_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    baseline_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # cold_start | learning | calibrated | mature
    personalization_level: Mapped[str] = mapped_column(String(20), nullable=False, default="cold_start")
    total_observation_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    total_valid_samples: Mapped[int] = mapped_column(Integer, default=0)
    total_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    false_alarm_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    sensor_error_count: Mapped[int] = mapped_column(Integer, default=0)
    typical_hr_min: Mapped[float] = mapped_column(Float, default=55.0)
    typical_hr_max: Mapped[float] = mapped_column(Float, default=100.0)
    typical_spo2_min: Mapped[float] = mapped_column(Float, default=95.0)
    typical_spo2_max: Mapped[float] = mapped_column(Float, default=100.0)
    typical_motion_min: Mapped[float] = mapped_column(Float, default=0.0)
    typical_motion_max: Mapped[float] = mapped_column(Float, default=0.5)
    # Gunun zamani ve aktivite baglamina ait JSON ozetlerini saklar.
    day_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    night_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activity_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ml_window_count: Mapped[int] = mapped_column(Integer, default=0)
    ml_usable_window_count: Mapped[int] = mapped_column(Integer, default=0)
    ml_evidence_mean: Mapped[float] = mapped_column(Float, default=0.0)
    ml_evidence_std: Mapped[float] = mapped_column(Float, default=0.0)
    ml_confidence_mean: Mapped[float] = mapped_column(Float, default=0.0)
    ml_positive_support_count: Mapped[int] = mapped_column(Integer, default=0)
    ml_personal_disagreement_count: Mapped[int] = mapped_column(Integer, default=0)
    last_ml_evidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_ml_adjustment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_model_window_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_recalibrated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PersonalRiskMemory(Base):
    # Gecmis risk olaylarini ve verilen tepkileri saklar.
    __tablename__ = "personal_risk_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # watch_entered | warning_entered | critical_entered | user_ok | user_not_ok | false_alarm | sensor_error
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PersonalTrendSnapshot(Base):
    # Kullanici icin kisa ve orta vadeli trend ozetlerini saklar.
    __tablename__ = "personal_trend_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    # rising | falling | stable
    hr_trend: Mapped[str] = mapped_column(String(10), default="stable")
    spo2_trend: Mapped[str] = mapped_column(String(10), default="stable")
    motion_trend: Mapped[str] = mapped_column(String(10), default="stable")
    quality_trend: Mapped[str] = mapped_column(String(10), default="stable")
    risk_trend: Mapped[str] = mapped_column(String(10), default="stable")
    trend_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ModelWindowLog(Base):
    # Ham ornekleri tutmadan model penceresi ustverisini saklar.
    __tablename__ = "model_window_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    window_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="real")
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    model_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_signal_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_evidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_adjustment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_base_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    personalized_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    personal_adjustment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_adjustment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    safety_adjustment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fusion_mode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# Bakim asistani durumunu kullanici bazinda saklar.
class AssistantState(Base):
    __tablename__ = "assistant_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    # normal | watch | warning | critical
    current_mode: Mapped[str] = mapped_column(String(20), default="normal")
    previous_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    personalization_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    watch_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    warning_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    critical_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    awaiting_user_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    ack_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # ok | not_ok | false_alarm | no_response
    last_user_response: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_action_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # normal | increased | urgent
    monitoring_intensity: Mapped[str] = mapped_column(String(20), default="normal")
    recommended_poll_interval_sec: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssistantAction(Base):
    # Bakim asistaninin kullanici icin urettigi aksiyonu saklar.
    __tablename__ = "assistant_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    state_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="normal")
    # observe | increase_monitoring | show_guidance | ask_are_you_ok | sound_alarm
    # notify_relative | notify_doctor | return_to_watch | record_feedback
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # low | medium | high | critical
    priority: Mapped[str] = mapped_column(String(10), default="low")
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    ack_options: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AssistantAcknowledgement(Base):
    # Kullanici yanitlarini ve aksiyon baglantisini saklar.
    __tablename__ = "assistant_acknowledgements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    state_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # ok | not_ok | false_alarm
    response: Mapped[str] = mapped_column(String(20), nullable=False)
    # self | relative | doctor
    response_source: Mapped[str] = mapped_column(String(20), default="self")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
