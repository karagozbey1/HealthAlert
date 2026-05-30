
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from repositories.factory import RepoSet

logger = logging.getLogger("ai_bridge")

_RISK_LEVEL_MAP = {
    "critical": "critical",
    "warning": "warning",
    "watch": "watch",
    "normal": None,
}

# AI postprocessor çıktısını backend repository katmanına aktarır.
async def process_ai_result(
    repos: RepoSet,
    user_id: str,
    ai_output: Dict[str, Any],
    vitals: Optional[Dict[str, float]] = None,
    db=None,
) -> Dict[str, Any]:
    """ai bridge servisindeki HealthAlert iş kuralını uygular."""
    risk_level = ai_output.get("final_risk_level", "normal")
    severity = _RISK_LEVEL_MAP.get(risk_level)
    early_risk = ai_output.get("early_risk_score", 0.0)
    fall_prob = ai_output.get("fall_probability", 0.0)
    instability_prob = ai_output.get("instability_probability", 0.0)
    recommendations: List[str] = ai_output.get("recommendations", [])
    reasons: List[str] = ai_output.get("reasons", [])
    immediate_alert: bool = ai_output.get("immediate_alert", False)
    confidence: float = ai_output.get("confidence", 1.0)

    created: Dict[str, Any] = {
        "risk_level": risk_level,
        "anomaly_id": None,
        "alert_id": None,
        "notifications_sent": 0,
    }

    if vitals:
        await repos.live_status.upsert(user_id, {
            "heart_rate": vitals.get("heart_rate", 72.0),
            "spo2": vitals.get("spo2", 98.0),
            "motion_score": instability_prob,
            "risk_score": early_risk,
            "scenario": risk_level,
            "timestamp": datetime.utcnow(),
        })

    if severity is not None:
        metric, value, unit, summary = _pick_dominant_metric(
            ai_output, vitals or {}
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
            "title": f"{metric} anomaly (AI)",
            "subtitle": f"{value:.2f} {unit}",
            "severity": severity,
        })
        created["anomaly_id"] = anom_id

        if severity in ("warning", "critical") or immediate_alert:
            active_alert = await repos.alerts.get_active_by_user(user_id)
            if active_alert is None:
                alert_id = str(uuid4())
                countdown = 15 if immediate_alert else (30 if severity == "critical" else 20)
                await repos.alerts.create({
                    "id": alert_id,
                    "user_id": user_id,
                    "title": f"{metric} Alert (AI)",
                    "description": summary,
                    "severity": severity,
                    "status": "countdown",
                    "countdown_total_sec": countdown,
                    "countdown_remaining_sec": countdown,
                    "recommendations": recommendations,
                    "related_anomaly_id": anom_id,
                })
                await repos.history.create({
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "item_type": "alert",
                    "title": f"{metric} Alert (AI)",
                    "subtitle": summary,
                    "severity": severity,
                })
                created["alert_id"] = alert_id

                user_obj = await repos.users.get_by_id(user_id)
                user_name = user_obj["full_name"] if user_obj else "Unknown"
                relations = await repos.relations.find_active_by_self_user(user_id)
                for rel in relations:
                    notif_body = f"{user_name}: {summary}"
                    await repos.notifications.create({
                        "id": str(uuid4()),
                        "recipient_id": rel["linked_user_id"],
                        "sender_id": user_id,
                        "title": f"🤖 AI Alert: {metric}",
                        "body": notif_body,
                        "notification_type": "alert",
                        "reference_id": alert_id,
                        "reference_type": "alert",
                        "is_read": False,
                    })
                    created["notifications_sent"] += 1

                    if db is not None:
                        try:
                            from services.push_service import push_to_user
                            await push_to_user(
                                db, rel["linked_user_id"],
                                f"🤖 AI Alert: {metric}", notif_body,
                                data={
                                    "type": "alert",
                                    "reference_id": alert_id,
                                },
                            )
                        except Exception as exc:
                            logger.debug("Push delivery skipped in AI bridge: %s", exc)

    logger.info(
        "AI result ingested for user=%s  risk=%s  anomaly=%s  alert=%s  notifs=%d",
        user_id, risk_level, created["anomaly_id"], created["alert_id"],
        created["notifications_sent"],
    )
    return created

# AI çıktısından baskın sağlık metriğini seçer.
def _pick_dominant_metric(
    ai_output: Dict[str, Any],
    vitals: Dict[str, float],
) -> tuple[str, float, str, str]:
    """ai bridge servisindeki HealthAlert iş kuralını uygular."""
    fall_prob = ai_output.get("fall_probability", 0.0)
    instability_prob = ai_output.get("instability_probability", 0.0)
    hr = vitals.get("heart_rate", 72.0)
    spo2 = vitals.get("spo2", 98.0)

    if fall_prob >= 0.6:
        return ("Fall Risk", fall_prob, "prob", f"AI fall probability {fall_prob:.0%}.")
    if spo2 < 92:
        return ("SpO2", spo2, "%", f"Oxygen saturation critically low at {spo2:.1f}%.")
    if hr > 120 or hr < 50:
        label = "elevated" if hr > 120 else "dangerously low"
        return ("Heart Rate", hr, "bpm", f"Heart rate {label} at {hr:.1f} bpm.")
    if instability_prob >= 0.5:
        return ("Instability", instability_prob, "prob", f"AI instability score {instability_prob:.0%}.")
    risk = ai_output.get("early_risk_score", 0.0)
    return ("Combined Risk", risk, "score", "Multiple AI metrics outside expected range.")
