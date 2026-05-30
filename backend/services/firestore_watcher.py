from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from config import settings

logger = logging.getLogger("firestore_watcher")

try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ModuleNotFoundError:
    FieldFilter = None

_last_processed: Dict[str, float] = {}

# IMU ve gyro verisinden basit hareket skorunu hesaplar.
def _compute_motion_score(ax: float, ay: float, az: float,
                          gx: float, gy: float, gz: float) -> float:
    """firestore watcher servisinde risk veya skor değerini hesaplar."""
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)

# Nabiz, SpO2 ve hareketten heuristik risk skoru uretir.
def _compute_risk_score(hr: float, spo2: float, hr_valid: bool,
                        spo2_valid: bool, motion: float) -> float:
    """firestore watcher servisinde risk veya skor değerini hesaplar."""
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

# Risk skorunu severity etiketine cevirir.
def _risk_to_severity(risk: float) -> Optional[str]:
    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
    if risk >= settings.RISK_CRITICAL_THRESHOLD:
        return "critical"
    if risk >= settings.RISK_WARNING_THRESHOLD:
        return "warning"
    if risk >= settings.RISK_WATCH_THRESHOLD:
        return "watch"
    return None

# Alarm ozeti icin baskin metriği ve aciklamayi belirler.
def _determine_anomaly_metric(hr, spo2, hr_valid, spo2_valid, motion):
    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
    if spo2_valid and spo2 < 92:
        return ("SpO2", spo2, "%", f"Oxygen saturation critically low at {spo2:.1f}%.")
    if hr_valid and hr > 120:
        return ("Heart Rate", hr, "bpm", f"Heart rate elevated at {hr:.1f} bpm.")
    if hr_valid and hr < 50:
        return ("Heart Rate", hr, "bpm", f"Heart rate dangerously low at {hr:.1f} bpm.")
    if motion > 0.6:
        return ("Motion", motion, "score", "Unusual movement detected.")
    if spo2_valid and spo2 < 94:
        return ("SpO2", spo2, "%", f"Oxygen saturation below normal at {spo2:.1f}%.")
    if hr_valid and hr > 100:
        return ("Heart Rate", hr, "bpm", f"Heart rate mildly elevated at {hr:.1f} bpm.")
    return ("Combined", 0.0, "score", "Multiple metrics outside expected range.")

# Önem derecesine göre öneri listesi döndürür.
def _get_recommendations(severity: str):
    """firestore watcher servisinde gereken veriyi okuyup çağırana döndürür."""
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

# Firestore paketini mevcut repository akisi uzerinden backend kayitlarina isler.
async def _process_firestore_packet(
    doc_data: Dict[str, Any],
    repos,
    db,
) -> None:
    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
    device_id = doc_data.get("device_id", "")
    user_id = doc_data.get("user_id", "")
    packet_seq = doc_data.get("packet_seq", 0)

    if not user_id:
        reg = await repos.devices.get_registration(device_id)
        if reg:
            user_id = reg["user_id"]

    if not user_id:
        logger.debug("No user_id for device %s packet %d — skipped", device_id, packet_seq)
        return

    hr = float(doc_data.get("heart_rate", 72))
    spo2 = float(doc_data.get("spo2", 98))
    hr_valid = bool(doc_data.get("hr_valid", True))
    spo2_valid = bool(doc_data.get("spo2_valid", True))
    ax = float(doc_data.get("accel_x", 0))
    ay = float(doc_data.get("accel_y", 0))
    az = float(doc_data.get("accel_z", 1))
    gx = float(doc_data.get("gyro_x", 0))
    gy = float(doc_data.get("gyro_y", 0))
    gz = float(doc_data.get("gyro_z", 0))

    motion_score = _compute_motion_score(ax, ay, az, gx, gy, gz)
    risk_score = _compute_risk_score(hr, spo2, hr_valid, spo2_valid, motion_score)

    hr_display = max(20.0, min(250.0, hr if hr_valid else 72.0))
    spo2_display = max(50.0, min(100.0, spo2 if spo2_valid else 98.0))

    await repos.live_status.upsert(user_id, {
        "heart_rate": hr_display,
        "spo2": spo2_display,
        "motion_score": motion_score,
        "risk_score": risk_score,
        "scenario": doc_data.get("state_hint", "normal"),
        "timestamp": datetime.utcnow(),
    })

    severity = _risk_to_severity(risk_score)
    if severity is not None:
        metric, value, unit, summary = _determine_anomaly_metric(
            hr, spo2, hr_valid, spo2_valid, motion_score,
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

    await db.commit()
    logger.debug("Processed Firestore packet: device=%s user=%s seq=%d risk=%.3f",
                 device_id, user_id, packet_seq, risk_score)

# Islenmemis Firestore telemetry kayitlarini cekip tek tek isler.
async def poll_firestore_telemetry(repos, db) -> int:
    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
    from firebase_client import get_firestore_client

    client = get_firestore_client()
    if client is None:
        return 0

    processed = 0
    try:
        loop = asyncio.get_event_loop()

        def _query():
            """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
            col = client.collection("telemetry_packets")
            if FieldFilter is None:
                query = (
                    col.where("backend_processed", "==", False)
                    .order_by("timestamp_ms")
                    .limit(50)
                )
            else:
                query = (
                    col.where(filter=FieldFilter("backend_processed", "==", False))
                    .order_by("timestamp_ms")
                    .limit(50)
                )
            try:
                return list(query.stream())
            except Exception:
                return list(
                    col.order_by("timestamp_ms", direction="DESCENDING")
                    .limit(50)
                    .stream()
                )

        docs = await loop.run_in_executor(None, _query)

        for doc in docs:
            doc_data = doc.to_dict()
            if not doc_data:
                continue

            if doc_data.get("backend_processed"):
                continue

            device_id = doc_data.get("device_id", "")
            ts = doc_data.get("timestamp_ms", 0)
            key = f"{device_id}:{ts}"
            if key in _last_processed:
                continue

            try:
                await _process_firestore_packet(doc_data, repos, db)
                processed += 1
                _last_processed[key] = ts

                def _mark_processed(doc_ref=doc.reference):
                    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
                    doc_ref.update({"backend_processed": True})

                await loop.run_in_executor(None, _mark_processed)

            except Exception as exc:
                logger.error("Error processing Firestore packet %s: %s",
                             doc.id, exc, exc_info=True)

        if len(_last_processed) > 5000:
            keys = list(_last_processed.keys())
            for k in keys[:2500]:
                del _last_processed[k]

    except Exception as exc:
        logger.error("Firestore polling error: %s", exc, exc_info=True)

    return processed

# Firestore değişikliklerini dinler ve backend'e aktarır.
async def run_firestore_watcher_loop(repos, db_factory) -> None:
    """firestore watcher servisindeki HealthAlert iş kuralını uygular."""
    from firebase_client import get_firestore_client

    if settings.DATA_MODE not in ("firebase", "hybrid"):
        logger.info("Firestore watcher disabled (DATA_MODE=%s)", settings.DATA_MODE)
        return

    client = get_firestore_client()
    if client is None:
        logger.warning("Firestore watcher: no Firestore client available. Watcher disabled.")
        return

    logger.info("Firestore watcher started (DATA_MODE=%s, poll_interval=%.1fs)",
                settings.DATA_MODE, settings.SIMULATION_INTERVAL_SECONDS)

    while True:
        try:
            async with db_factory() as db:
                from repositories.factory import get_repos
                repo_set = get_repos(db, settings.DATA_MODE)
                count = await poll_firestore_telemetry(repo_set, db)
                if count > 0:
                    logger.info("Firestore watcher: processed %d packets", count)
        except Exception as exc:
            logger.error("Firestore watcher loop error: %s", exc, exc_info=True)

        await asyncio.sleep(settings.SIMULATION_INTERVAL_SECONDS)
