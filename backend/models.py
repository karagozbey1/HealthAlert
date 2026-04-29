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

    def get_recommendations(self) -> list[str]:
        try:
            return json.loads(self.recommendations)
        except Exception:
            return []

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

class SimulationState(Base):
    __tablename__ = "simulation_states"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    scenario_index: Mapped[int] = mapped_column(Integer, default=0)
    tick_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
