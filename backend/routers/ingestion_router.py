from __future__ import annotations

import asyncio
import logging
import math
from collections import OrderedDict
from datetime import datetime
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
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
from services.adaptive_personalization_service import (
    adaptive_personalization_service,
    compute_personalized_risk,
    compute_trend_from_snapshots,
)
from services.care_assistant_service import care_assistant_service
from services.baseline_service import (
    apply_baseline_adjustment,
    compute_personal_deviation,
    compute_quality_confidence,
    update_user_baseline,
)
from services.learning_data_service import learning_data_service, should_capture_window
from services.live_window_buffer import live_window_buffer
from services.ml_inference_service import ml_inference_service
from services.retrieval_shadow_service import retrieval_shadow_service

logger = logging.getLogger("ingestion")

router = APIRouter(prefix="/ingest", tags=["device-ingestion"])

_DEDUP_MAX = 2000
_seen_packets: OrderedDict[str, bool] = OrderedDict()

# Son gorulen paketleri seq bazinda yinelenmeye karsi tutar.
def _is_duplicate(device_id: str, packet_seq: int) -> bool:
    key = f"{device_id}:{packet_seq}"
    if key in _seen_packets:
        return True
    _seen_packets[key] = True
    if len(_seen_packets) > _DEDUP_MAX:
        _seen_packets.popitem(last=False)
    return False

# IMU ve gyro verisinden normalize hareket skoru uretir.
def _compute_motion_score(ax: float, ay: float, az: float,
                          gx: float, gy: float, gz: float) -> float:
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)

# HR, SpO2 ve hareketten heuristik risk skoru hesaplar.
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

# Risk skorunu esiklere gore watch, warning veya critical'a cevirir.
def _risk_to_severity(risk: float, sensitivity_offset: float = 0.0) -> str | None:
    critical_t = settings.RISK_CRITICAL_THRESHOLD + sensitivity_offset
    warning_t = settings.RISK_WARNING_THRESHOLD + sensitivity_offset
    watch_t = settings.RISK_WATCH_THRESHOLD + sensitivity_offset
    if risk >= critical_t:
        return "critical"
    if risk >= warning_t:
        return "warning"
    if risk >= watch_t:
        return "watch"
    return None

# Onem derecesine gore kullaniciya yonelik sabit onerileri dondurur.
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

# Anomali icin baskin metrik, deger ve ozet metnini secer.
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

# Cihaz paketini tum risk ve shadow katmanlarindan gecirip kaydeder.
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
    risk_breakdown: dict | None = None        # Tum cikti kollari icin baslangic degeri.
    window_status: dict | None = None         # Part 2 cikti ozetini tasir.
    ml_shadow_result: dict | None = None      # ML shadow sonucu burada tutulur.
    retrieval_shadow_result: dict | None = None  # Retrieval shadow sonucu burada tutulur.
    personalization_result: dict | None = None   # Kisisellestirme sonucu burada tutulur.
    assistant_state_result: dict | None = None   # Asistan durum cikisi burada tutulur.
    assistant_actions_result: list | None = None  # Asistan aksiyon cikisi burada tutulur.
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
        global_risk_score = _compute_risk_score(
            pkt.heart_rate, pkt.spo2,
            pkt.hr_valid, pkt.spo2_valid, motion_score,
        )

        # Baseline katmani ile risk skorunu kullaniciya gore ayarlar.
        alert_sensitivity = "normal"
        risk_breakdown: dict | None = None

        if settings.BASELINE_ENABLED:
            try:
                # Kullanicinin alert duyarlilik ayarini alir.
                user_app_settings = await repos.app_settings.get_or_create(user_id)
                alert_sensitivity = user_app_settings.get("alert_sensitivity", "normal")

                # Sinyal kalitesinden guven skoru uretir.
                quality_info = compute_quality_confidence(
                    signal_quality=pkt.signal_quality,
                    finger_detected=pkt.finger_detected,
                    hr_valid=pkt.hr_valid,
                    spo2_valid=pkt.spo2_valid,
                    ppg_ok=pkt.ppg_ok,
                    spo2=pkt.spo2,
                    spo2_valid_flag=pkt.spo2_valid,
                )

                # Guvenilir paketlerde baseline kaydini gunceller.
                baseline = await update_user_baseline(
                    repos=repos,
                    user_id=user_id,
                    packet_mode=pkt.mode,
                    finger_detected=pkt.finger_detected,
                    hr_valid=pkt.hr_valid,
                    spo2_valid=pkt.spo2_valid,
                    signal_quality=pkt.signal_quality,
                    ppg_ok=pkt.ppg_ok,
                    imu_ok=pkt.imu_ok,
                    hr=pkt.heart_rate,
                    spo2=pkt.spo2,
                    motion_score=motion_score,
                    global_risk_score=global_risk_score,
                )

                baseline_ready = baseline.get("is_ready", False)

                # Kisisel baseline'dan anlik sapmayi hesaplar.
                deviation = compute_personal_deviation(
                    baseline=baseline,
                    hr=pkt.heart_rate,
                    spo2=pkt.spo2,
                    motion_score=motion_score,
                    hr_valid=pkt.hr_valid,
                    spo2_valid=pkt.spo2_valid,
                )

                # Baseline ve kalite etkisini nihai riske uygular.
                adjustment = apply_baseline_adjustment(
                    global_risk_score=global_risk_score,
                    deviation=deviation,
                    quality_info=quality_info,
                    baseline_ready=baseline_ready,
                    alert_sensitivity=alert_sensitivity,
                )
                risk_score = adjustment["final_risk_score"]
                risk_breakdown = adjustment

                # Part 5B kisisellestirme katmani riski ek baglamla zenginlestirir.
                try:
                    if (
                        settings.PERSONALIZATION_ENABLED
                        and repos.personalization is not None
                        and pkt.mode == "real"
                    ):
                        # Kisisel profil kaydini gunceller.
                        profile = await adaptive_personalization_service.update_profile_from_packet(
                            repos=repos,
                            user_id=user_id,
                            hr=pkt.heart_rate,
                            spo2=pkt.spo2,
                            motion_score=motion_score,
                            hr_valid=pkt.hr_valid,
                            spo2_valid=pkt.spo2_valid,
                            baseline=baseline,
                        )

                        # Trend icin simdilik MVP duzeyinde anlik gorunum kullanilir.
                        trend_info = compute_trend_from_snapshots([])

                        personalization_result = compute_personalized_risk(
                            global_risk_score=global_risk_score,
                            baseline_result=adjustment,
                            profile=profile,
                            trend_info=trend_info,
                            quality_info=quality_info,
                            hr=pkt.heart_rate,
                            spo2=pkt.spo2,
                            motion_score=motion_score,
                            hr_valid=pkt.hr_valid,
                            spo2_valid=pkt.spo2_valid,
                            severity=_risk_to_severity(adjustment["final_risk_score"]),
                        )
                        # Kisisellestirilmis final risk degerini uygular.
                        risk_score = personalization_result["final_personalized_risk"]
                        risk_breakdown = dict(adjustment)
                        risk_breakdown["final_risk_score"] = risk_score
                        risk_breakdown["personalization"] = {
                            "personalization_level": personalization_result["personalization_level"],
                            "baseline_deviation_score": personalization_result["baseline_deviation_score"],
                            "trend_adjustment": personalization_result["trend_adjustment"],
                            "feedback_adjustment": personalization_result["feedback_adjustment"],
                            "confidence": personalization_result["confidence"],
                        }
                except Exception as _p_exc:
                    logger.warning(
                        "Personalization error for user=%s (ignored): %s", user_id, _p_exc
                    )
            except Exception as exc:
                logger.warning("Baseline adjustment failed for user %s: %s", user_id, exc, exc_info=True)
                risk_score = global_risk_score
        else:
            risk_score = global_risk_score

        # Severity icin hassasiyet kaymasini risk skoruna gore hesaplar.
        sensitivity_offset = 0.0
        if alert_sensitivity == "high":
            sensitivity_offset = -0.10
        elif alert_sensitivity == "low":
            sensitivity_offset = 0.10

        existing = await repos.live_status.get_by_user(user_id)
        # When invalid, store 0.0 — NOT the stale 72/98 defaults.
        # hr_valid/spo2_valid come from the DevicePacketLog enrichment in
        # repos.live_status.get_by_user(), so the mobile always gets the
        # correct validity flag regardless of what heart_rate value is stored.
        hr_display   = pkt.heart_rate if pkt.hr_valid  else 0.0
        spo2_display = pkt.spo2       if pkt.spo2_valid else 0.0

        if hr_display > 0:
            hr_display = max(20.0, min(250.0, hr_display))
        if spo2_display > 0:
            spo2_display = max(50.0, min(100.0, spo2_display))

        await repos.live_status.upsert(user_id, {
            "heart_rate": hr_display,
            "spo2": spo2_display,
            "motion_score": motion_score,
            "risk_score": risk_score,
            "scenario": pkt.state_hint or "normal",
            "timestamp": datetime.utcnow(),
        })

        severity: str | None = None   # Asistan akisinda da kullanilacagi icin once tanimlanir.
        try:
            severity = _risk_to_severity(risk_score, sensitivity_offset)
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

        # Part 2 buffer ve ML shadow akisi response metadata'sini gunceller.
        try:
            qc = (
                risk_breakdown.get("quality_confidence", 1.0)
                if risk_breakdown
                else 1.0
            )
            window_status = live_window_buffer.add_packet(
                user_id=user_id,
                packet=pkt,
                motion_score=motion_score,
                final_risk_score=risk_score,
                quality_confidence=qc,
            )

            if (
                settings.ML_INFERENCE_ENABLED
                and live_window_buffer.should_run_inference(user_id)
            ):
                window = live_window_buffer.get_window(user_id)
                if window:
                    ml_shadow_result = await asyncio.to_thread(
                        ml_inference_service.predict_window,
                        user_id,
                        window,
                        None,
                        window_status,
                    )
                    if ml_shadow_result:
                        ml_shadow_result["window_status"] = window_status
                    logger.info(
                        "ML shadow inference user=%s risk_level=%s latency=%.1fms",
                        user_id,
                        ml_shadow_result.get("ml_final_risk_level") if ml_shadow_result else None,
                        (ml_shadow_result.get("inference_latency_ms") or 0) if ml_shadow_result else 0,
                    )
            elif settings.ML_INFERENCE_ENABLED and not window_status.get("is_full"):
                logger.debug(
                    "ML shadow: buffer not ready for user=%s (%d/%d packets)",
                    user_id,
                    window_status.get("current_size", 0),
                    settings.ML_WINDOW_SIZE,
                )
        except Exception as exc:
            logger.warning(
                "Live window / ML shadow error for user=%s (ignored): %s",
                user_id,
                exc,
            )

        # Part 3 retrieval shadow sonucu yalnizca izleme metadata'si uretir.
        try:
            if settings.RETRIEVAL_ENABLED and window_status is not None:
                ws_full = window_status.get("is_full", False)
                if ws_full:
                    window = live_window_buffer.get_window(user_id)
                    if window:
                        retrieval_shadow_result = await asyncio.to_thread(
                            retrieval_shadow_service.query_window,
                            window,
                            window_status,
                        )
                        if retrieval_shadow_result:
                            retrieval_shadow_result["window_status"] = window_status
                        logger.info(
                            "Retrieval shadow user=%s support=%.3f low_confidence=%s",
                            user_id,
                            (retrieval_shadow_result or {}).get("support_score", 0.0),
                            (retrieval_shadow_result or {}).get("low_confidence", True),
                        )
                elif settings.RETRIEVAL_ENABLED:
                    logger.debug(
                        "Retrieval shadow: buffer not full for user=%s (%d/%d)",
                        user_id,
                        window_status.get("current_size", 0),
                        settings.ML_WINDOW_SIZE,
                    )
        except Exception as exc:
            logger.warning(
                "Retrieval shadow error for user=%s (ignored): %s",
                user_id,
                exc,
            )

        # Part 5A ogrenme dongusu offline egitim icin pencere kaydi olusturur.
        learning_capture_result: dict | None = None
        try:
            if settings.LEARNING_LOOP_ENABLED and risk_breakdown is not None:
                qc_for_learning = (
                    risk_breakdown.get("quality_confidence", 1.0)
                    if risk_breakdown
                    else 1.0
                )
                severity_now = _risk_to_severity(risk_score, sensitivity_offset)
                if should_capture_window(
                    user_id=user_id,
                    packet_mode=pkt.mode,
                    final_risk_score=risk_score,
                    quality_confidence=qc_for_learning,
                    risk_level=severity_now,
                    baseline_ready=risk_breakdown.get("baseline_ready", False),
                ):
                    learning_capture_result = await learning_data_service.build_and_save_window(
                        repos=repos,
                        user_id=user_id,
                        device_id=pkt.device_id,
                        packet_mode=pkt.mode,
                        final_risk_score=risk_score,
                        quality_confidence=qc_for_learning,
                        risk_level=severity_now,
                        baseline_ready=risk_breakdown.get("baseline_ready", False),
                        risk_breakdown=risk_breakdown,
                        window_status=window_status,
                        ml_shadow_result=ml_shadow_result,
                        retrieval_shadow_result=retrieval_shadow_result,
                    )
                    if learning_capture_result:
                        logger.debug(
                            "Learning capture user=%s window=%s candidate=%s label=%s",
                            user_id,
                            learning_capture_result.get("window_id"),
                            learning_capture_result.get("training_candidate"),
                            learning_capture_result.get("suggested_label"),
                        )
        except Exception as exc:
            logger.warning(
                "Learning loop error for user=%s (ignored): %s", user_id, exc
            )

        # Part 5C bakim asistani mod gecisi ve aksiyonlari hesaplar.
        try:
            if settings.ASSISTANT_ENABLED and repos.assistant is not None:
                eval_result = await care_assistant_service.evaluate_assistant_state(
                    repos=repos,
                    user_id=user_id,
                    final_risk_score=risk_score,
                    severity=severity,
                    risk_breakdown=risk_breakdown,
                )
                assistant_state_result = eval_result
                assistant_actions_result = eval_result.get("actions_created")
        except Exception as _a_exc:
            logger.warning("Care assistant error for user=%s (ignored): %s", user_id, _a_exc)

    await db.commit()

    logger.info("Ingested packet seq=%d from device=%s (user=%s)",
                pkt.packet_seq, pkt.device_id, user_id or "unmapped")

    include_ml = (
        settings.ML_INFERENCE_ENABLED
        and settings.ML_RESPONSE_INCLUDE_SHADOW_RESULT
    )
    include_retrieval = (
        settings.RETRIEVAL_ENABLED
        and settings.RETRIEVAL_RESPONSE_INCLUDE_RESULT
    )
    return DevicePacketResponse(
        status="accepted",
        packet_seq=pkt.packet_seq,
        device_id=pkt.device_id,
        user_id=user_id,
        risk_breakdown=risk_breakdown,
        window_status=window_status if user_id else None,
        ml_shadow_result=ml_shadow_result if (user_id and include_ml) else None,
        retrieval_shadow_result=(
            retrieval_shadow_result if (user_id and include_retrieval) else None
        ),
        learning_capture_result=(
            learning_capture_result if (user_id and settings.LEARNING_LOOP_ENABLED) else None
        ),
        personalization_result=(
            personalization_result if (user_id and settings.PERSONALIZATION_ENABLED) else None
        ),
        assistant_state=assistant_state_result if (user_id and settings.ASSISTANT_ENABLED) else None,
        assistant_actions=assistant_actions_result if (user_id and settings.ASSISTANT_ENABLED) else None,
    )

# Cihazi SELF kullanicisi ile esler veya kaydi gunceller.
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

# Cihazin sahiplik ve aktiflik durumunu dondurur.
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

# Harici AI sonucunu legacy kopru uzerinden sisteme uygular.
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
