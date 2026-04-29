from __future__ import annotations

import logging
import math
from collections import OrderedDict
from datetime import datetime
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import (
    AIInferenceRequest,
    AIInferenceResponse,
    DevicePacketRequest,
    DevicePacketResponse,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
)
from services.ai_bridge import process_ai_result

logger = logging.getLogger("ingestion")

router = APIRouter(prefix="/ingest", tags=["device-ingestion"])

_DEDUP_MAX = 2000
_seen_packets: OrderedDict[str, bool] = OrderedDict()

def _is_duplicate(device_id: str, packet_seq: int) -> bool:
    key = f"{device_id}:{packet_seq}"
    if key in _seen_packets:
        return True
    _seen_packets[key] = True
    if len(_seen_packets) > _DEDUP_MAX:
        _seen_packets.popitem(last=False)
    return False

def _compute_motion_score(ax: float, ay: float, az: float,
                          gx: float, gy: float, gz: float) -> float:
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)

def _compute_risk_score(hr: float, spo2: float, hr_valid: bool,
                        spo2_valid: bool, motion: float) -> float:
    risk = 0.0
    if hr_valid:
        if hr > 120:
            risk += 0.3
        elif hr > 100:
            risk += 0.15
        elif hr < 50:
            risk += 0.2
    if spo2_valid:
        if spo2 < 90:
            risk += 0.4
        elif spo2 < 94:
            risk += 0.2
    risk += motion * 0.2
    return round(min(1.0, risk), 3)

def _risk_to_severity(risk: float) -> str | None:
    from config import settings
    if risk >= settings.RISK_CRITICAL_THRESHOLD:
        return "critical"
    if risk >= settings.RISK_WARNING_THRESHOLD:
        return "warning"
    if risk >= settings.RISK_WATCH_THRESHOLD:
        return "watch"
    return None

# Önem derecesine göre öneri listesi döndürür.
def _get_recommendations(severity: str) -> List[str]:
    if severity == "critical":
        return [
            "Emergency risk detected.",
            "Stay where you are and wait for assistance.",
            "If conscious, press Emergency now.",
        ]
    if severity == "warning":
        return [
            "Sit down and stay calm.",
            "Monitor vitals for 2 minutes.",
            "Contact a caregiver if symptoms persist.",
        ]
    return ["Reduce physical exertion.", "Hydrate and rest."]

def _determine_anomaly_metric(hr: float, spo2: float, hr_valid: bool,
                               spo2_valid: bool, motion: float) -> tuple[str, float, str, str]:
    if spo2_valid and spo2 < 92:
        return ("SpO2", spo2, "%", f"Oxygen saturation critically low at {spo2:.1f}%.")
    if hr_valid and hr > 120:
        return ("Heart Rate", hr, "bpm", f"Heart rate elevated at {hr:.1f} bpm.")
    if hr_valid and hr < 50:
        return ("Heart Rate", hr, "bpm", f"Heart rate dangerously low at {hr:.1f} bpm.")
    if motion > 0.6:
        return ("Motion", motion, "score", "Unusual movement detected. Possible instability or fall risk.")
    if spo2_valid and spo2 < 94:
        return ("SpO2", spo2, "%", f"Oxygen saturation below normal at {spo2:.1f}%.")
    if hr_valid and hr > 100:
        return ("Heart Rate", hr, "bpm", f"Heart rate mildly elevated at {hr:.1f} bpm.")
    return ("Combined", 0.0, "score", "Multiple metrics outside expected range.")

@router.post("/device-packet", response_model=DevicePacketResponse)
async def ingest_device_packet(
    pkt: DevicePacketRequest,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
):
    if _is_duplicate(pkt.device_id, pkt.packet_seq):
        logger.debug("Duplicate packet seq=%d from device=%s — skipped.",
                      pkt.packet_seq, pkt.device_id)
        return DevicePacketResponse(
            status="duplicate",
            packet_seq=pkt.packet_seq,
            device_id=pkt.device_id,
        )

    user_id = None
    reg = await repos.devices.get_registration(pkt.device_id)
    if reg:
        user_id = reg["user_id"]

    await repos.devices.log_packet({
        "id": str(uuid4()),
        "device_id": pkt.device_id,
        "user_id": user_id,
        "timestamp_ms": pkt.timestamp_ms,
        "mode": pkt.mode,
        "packet_seq": pkt.packet_seq,
        "accel_x": pkt.accel_x, "accel_y": pkt.accel_y, "accel_z": pkt.accel_z,
        "gyro_x": pkt.gyro_x, "gyro_y": pkt.gyro_y, "gyro_z": pkt.gyro_z,
        "red_value": pkt.red_value, "ir_value": pkt.ir_value,
        "heart_rate": pkt.heart_rate, "spo2": pkt.spo2,
        "signal_quality": pkt.signal_quality,
        "imu_ok": pkt.imu_ok, "ppg_ok": pkt.ppg_ok,
        "hr_valid": pkt.hr_valid, "spo2_valid": pkt.spo2_valid,
        "finger_detected": pkt.finger_detected,
        "state_hint": pkt.state_hint or "normal",
    })

    if user_id:
        motion_score = _compute_motion_score(
            pkt.accel_x, pkt.accel_y, pkt.accel_z,
            pkt.gyro_x, pkt.gyro_y, pkt.gyro_z,
        )
        risk_score = _compute_risk_score(
            pkt.heart_rate, pkt.spo2,
            pkt.hr_valid, pkt.spo2_valid, motion_score,
        )

        existing = await repos.live_status.get_by_user(user_id)
        hr_display = pkt.heart_rate if pkt.hr_valid else (existing["heart_rate"] if existing else 72.0)
        spo2_display = pkt.spo2 if pkt.spo2_valid else (existing["spo2"] if existing else 98.0)

        hr_display = max(20.0, min(250.0, hr_display))
        spo2_display = max(50.0, min(100.0, spo2_display))

        await repos.live_status.upsert(user_id, {
            "heart_rate": hr_display,
            "spo2": spo2_display,
            "motion_score": motion_score,
            "risk_score": risk_score,
            "scenario": pkt.state_hint or "normal",
            "timestamp": datetime.utcnow(),
        })

        try:
            severity = _risk_to_severity(risk_score)
            if severity is not None:
                metric, value, unit, summary = _determine_anomaly_metric(
                    pkt.heart_rate, pkt.spo2, pkt.hr_valid, pkt.spo2_valid, motion_score,
                )
                anom_id = str(uuid4())
                await repos.anomalies.create({
                    "id": anom_id,
                    "user_id": user_id,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "severity": severity,
                    "summary": summary,
                })
                await repos.history.create({
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "item_type": "anomaly",
                    "title": f"{metric} anomaly",
                    "subtitle": f"{value:.1f} {unit}",
                    "severity": severity,
                })

                if severity in ("warning", "critical"):
                    active_alert = await repos.alerts.get_active_by_user(user_id)
                    if active_alert is None:
                        recs = _get_recommendations(severity)
                        alert_id = str(uuid4())
                        countdown = 30 if severity == "critical" else 20
                        await repos.alerts.create({
                            "id": alert_id,
                            "user_id": user_id,
                            "title": f"{metric} Alert",
                            "description": summary,
                            "severity": severity,
                            "status": "countdown",
                            "countdown_total_sec": countdown,
                            "countdown_remaining_sec": countdown,
                            "recommendations": recs,
                            "related_anomaly_id": anom_id,
                        })
                        await repos.history.create({
                            "id": str(uuid4()),
                            "user_id": user_id,
                            "item_type": "alert",
                            "title": f"{metric} Alert",
                            "subtitle": summary,
                            "severity": severity,
                        })
                        user_obj = await repos.users.get_by_id(user_id)
                        user_name = user_obj["full_name"] if user_obj else "Unknown"
                        from services.notification import notify_linked_users
                        await notify_linked_users(
                            db, user_id, user_name,
                            f"🚨 Alert: {metric} Alert", summary,
                            "alert",
                            reference_id=alert_id,
                            reference_type="alert",
                            repos=repos,
                        )
        except Exception as exc:
            logger.error("Anomaly/alert chain error for user %s: %s", user_id, exc, exc_info=True)

    await db.commit()

    logger.info("Ingested packet seq=%d from device=%s (user=%s)",
                pkt.packet_seq, pkt.device_id, user_id or "unmapped")

    return DevicePacketResponse(
        status="accepted",
        packet_seq=pkt.packet_seq,
        device_id=pkt.device_id,
        user_id=user_id,
    )

@router.post("/register-device", response_model=DeviceRegistrationResponse)
async def register_device(
    req: DeviceRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="Only SELF users can register devices.")

    existing = await repos.devices.get_registration(req.device_id)
    if existing:
        if existing["user_id"] == current_user.id and existing["is_active"]:
            return existing
        await repos.devices.update_registration(req.device_id, {
            "user_id": current_user.id,
            "is_active": True,
            "registered_at": datetime.utcnow(),
        })
        await db.commit()
        updated = await repos.devices.get_registration(req.device_id)
        return updated

    reg = await repos.devices.register_device({
        "id": str(uuid4()),
        "device_id": req.device_id,
        "user_id": current_user.id,
    })
    await db.commit()
    logger.info("Device '%s' registered to user '%s'.", req.device_id, current_user.id)
    return reg

@router.get("/device-status/{device_id}")
async def get_device_status(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    reg = await repos.devices.get_registration(device_id)
    if reg is None:
        raise HTTPException(status_code=404, detail="Device not registered.")

    if reg["user_id"] != current_user.id:
        relations = await repos.relations.find_active_by_self_user(reg["user_id"])
        linked_ids = [r["linked_user_id"] for r in relations]
        if current_user.id not in linked_ids:
            raise HTTPException(status_code=403, detail="Not authorized to view this device.")

    return {
        "device_id": reg["device_id"],
        "user_id": reg["user_id"],
        "is_active": reg["is_active"],
        "registered_at": reg["registered_at"].isoformat() if hasattr(reg["registered_at"], "isoformat") else str(reg["registered_at"]),
    }

@router.post("/ai-result", response_model=AIInferenceResponse)
async def ingest_ai_result(
    req: AIInferenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    vitals = None
    if req.heart_rate is not None or req.spo2 is not None:
        vitals = {
            "heart_rate": req.heart_rate or 72.0,
            "spo2": req.spo2 or 98.0,
        }

    ai_output = {
        "fall_probability": req.fall_probability,
        "instability_probability": req.instability_probability,
        "ppg_quality_score": req.ppg_quality_score,
        "vital_confidence_score": req.vital_confidence_score,
        "early_risk_score": req.early_risk_score,
        "final_risk_level": req.final_risk_level,
        "immediate_alert": req.immediate_alert,
        "confidence": req.confidence,
        "reasons": req.reasons,
        "recommendations": req.recommendations,
        "raw_scores": req.raw_scores or {},
    }

    result = await process_ai_result(repos, req.user_id, ai_output, vitals, db=db)
    await db.commit()

    return AIInferenceResponse(
        status="accepted",
        risk_level=result["risk_level"],
        anomaly_id=result.get("anomaly_id"),
        alert_id=result.get("alert_id"),
        notifications_sent=result.get("notifications_sent", 0),
    )
