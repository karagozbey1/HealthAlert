from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import List
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import User
from repositories.factory import RepoSet, get_repos

logger = logging.getLogger("simulation")

@dataclass
class Scenario:
    name: str
    hr_min: float
    hr_max: float
    spo2_min: float
    spo2_max: float
    motion_min: float
    motion_max: float
    risk_min: float
    risk_max: float
    ticks: int
    fires_anomaly: bool = False
    fires_alert: bool = False
    alert_severity: str = "normal"
    anomaly_metric: str = ""
    anomaly_unit: str = ""
    anomaly_summary: str = ""

SCENARIO_SEQUENCE: List[Scenario] = [
    Scenario("normal", 62, 72, 97, 99, 0.05, 0.2, 0.03, 0.12, 20),
    Scenario("elevated_hr", 95, 115, 96, 97, 0.3, 0.5, 0.35, 0.50, 8,
             fires_anomaly=True, alert_severity="warning",
             anomaly_metric="Nabız", anomaly_unit="bpm",
             anomaly_summary="Nabız normal aralığın üzerine çıkıyor."),
    Scenario("warning", 118, 130, 95, 96, 0.5, 0.7, 0.62, 0.70, 6,
             fires_anomaly=False, fires_alert=True, alert_severity="warning"),
    Scenario("normal", 62, 72, 97, 99, 0.05, 0.15, 0.04, 0.10, 15),
    Scenario("low_spo2", 72, 82, 88, 91, 0.2, 0.4, 0.80, 0.88, 8,
             fires_anomaly=True, fires_alert=True, alert_severity="critical",
             anomaly_metric="SpO2", anomaly_unit="%",
             anomaly_summary="Oksijen doygunluğu kritik seviyede düşük."),
    Scenario("recovery", 74, 84, 95, 98, 0.1, 0.3, 0.12, 0.22, 12),
    Scenario("normal", 62, 72, 97, 99, 0.05, 0.2, 0.03, 0.12, 25),
    Scenario("elevated_hr", 90, 108, 96, 97, 0.25, 0.45, 0.33, 0.48, 8,
             fires_anomaly=True, alert_severity="watch",
             anomaly_metric="Nabız", anomaly_unit="bpm",
             anomaly_summary="Yüksek nabız tespit edildi."),
    Scenario("motion_instability", 70, 85, 95, 97, 0.72, 0.95, 0.60, 0.82, 8,
             fires_anomaly=True, alert_severity="warning",
             anomaly_metric="Hareket", anomaly_unit="puan",
             anomaly_summary="Olağandışı hareket deseni tespit edildi. Olası denge sorunu veya düşme riski."),
    Scenario("normal", 62, 72, 97, 99, 0.05, 0.2, 0.03, 0.12, 30),
]

# Verilen aralıkta rastgele float üretir.
def _rng(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 1)

# Önem derecesine göre öneri listesi döndürür.
def _get_recommendations(severity: str) -> List[str]:
    if severity == "critical":
        return [
            "Acil risk tespit edildi.",
            "Bulunduğunuz yerde kalın ve yardım bekleyin.",
            "Bilinciniz yerindeyse şimdi Acil butonuna basın.",
        ]
    if severity == "warning":
        return [
            "Oturun ve sakin olun.",
            "2 dakika boyunca vital değerleri izleyin.",
            "Belirtiler devam ederse bir bakıcıyla iletişime geçin.",
        ]
    return ["Fiziksel aktiviteyi azaltın.", "Su için ve dinlenin."]

# Hastanın tüm bağlı yakın ve doktorlarına bildirim gönderir.
async def _fan_out_notification(
    repos: RepoSet,
    self_user_id: str,
    self_user_name: str,
    title: str,
    body: str,
    notif_type: str,
    reference_id: str,
    reference_type: str,
) -> None:
    relations = await repos.relations.find_active_by_self_user(self_user_id)
    for rel in relations:
        await repos.notifications.create({
            "id": str(uuid4()),
            "recipient_id": rel["linked_user_id"],
            "sender_id": self_user_id,
            "title": title,
            "body": f"{self_user_name}: {body}",
            "notification_type": notif_type,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "is_read": False,
        })

# Tek kullanıcı için bir simülasyon adımı işler.
async def _tick_user(db: AsyncSession, repos: RepoSet, user: User) -> None:
    state = await repos.simulation.get_or_create(user.id)
    seq_idx = state["scenario_index"] % len(SCENARIO_SEQUENCE)
    scenario = SCENARIO_SEQUENCE[seq_idx]
    tick_count = state["tick_count"]

    hr = _rng(scenario.hr_min, scenario.hr_max)
    spo2 = _rng(scenario.spo2_min, scenario.spo2_max)
    motion = _rng(scenario.motion_min, scenario.motion_max)
    risk = _rng(scenario.risk_min, scenario.risk_max)

    await repos.live_status.upsert(user.id, {
        "heart_rate": hr,
        "spo2": spo2,
        "motion_score": motion,
        "risk_score": risk,
        "scenario": scenario.name,
        "timestamp": datetime.utcnow(),
    })

    new_tick = tick_count + 1

    if tick_count == 0:
        if scenario.fires_anomaly:
            anomaly_value = hr if scenario.anomaly_unit == "bpm" else spo2
            anom_id = str(uuid4())
            await repos.anomalies.create({
                "id": anom_id,
                "user_id": user.id,
                "metric": scenario.anomaly_metric,
                "value": anomaly_value,
                "unit": scenario.anomaly_unit,
                "severity": scenario.alert_severity,
                "summary": scenario.anomaly_summary,
            })

            await repos.history.create({
                "id": str(uuid4()),
                "user_id": user.id,
                "item_type": "anomaly",
                "title": f"{scenario.anomaly_metric} anomalisi",
                "subtitle": f"{anomaly_value:.1f} {scenario.anomaly_unit}",
                "severity": scenario.alert_severity,
            })

            await _fan_out_notification(
                repos, user.id, user.full_name,
                f"Anomali: {scenario.anomaly_metric}",
                f"{anomaly_value:.1f} {scenario.anomaly_unit}",
                "anomaly", anom_id, "anomaly",
            )

        if scenario.fires_alert:
            active = await repos.alerts.get_active_by_user(user.id)
            if active is None:
                recs = _get_recommendations(scenario.alert_severity)
                alert_id = str(uuid4())
                countdown = 30 if scenario.alert_severity == "critical" else 20
                await repos.alerts.create({
                    "id": alert_id,
                    "user_id": user.id,
                    "title": f"{scenario.name.replace('_', ' ').title()} Alarmı",
                    "description": scenario.anomaly_summary or f"Sağlık metriği {scenario.alert_severity} bölgesine girdi.",
                    "severity": scenario.alert_severity,
                    "status": "countdown",
                    "countdown_total_sec": countdown,
                    "countdown_remaining_sec": countdown,
                    "recommendations": recs,
                })

                await repos.history.create({
                    "id": str(uuid4()),
                    "user_id": user.id,
                    "item_type": "alert",
                    "title": f"{scenario.name.replace('_', ' ').title()} Alarmı",
                    "subtitle": scenario.anomaly_summary or f"Sağlık metriği {scenario.alert_severity} bölgesine girdi.",
                    "severity": scenario.alert_severity,
                })

                await _fan_out_notification(
                    repos, user.id, user.full_name,
                    f"🚨 Alarm: {scenario.name.replace('_', ' ').title()}",
                    scenario.anomaly_summary or f"Sağlık metriği {scenario.alert_severity} bölgesine girdi.",
                    "alert", alert_id, "alert",
                )

    if new_tick >= scenario.ticks:
        await repos.simulation.update(user.id, {
            "scenario_index": (seq_idx + 1) % len(SCENARIO_SEQUENCE),
            "tick_count": 0,
            "last_updated": datetime.utcnow(),
        })
    else:
        await repos.simulation.update(user.id, {
            "tick_count": new_tick,
            "last_updated": datetime.utcnow(),
        })

    countdown_alerts = await repos.alerts.get_countdown_alerts(user.id)
    for alert in countdown_alerts:
        remaining = alert["countdown_remaining_sec"] - 1
        if remaining <= 0:
            await repos.alerts.update(alert["id"], {
                "countdown_remaining_sec": 0,
                "status": "post_event_monitoring",
            })
            await _fan_out_notification(
                repos, user.id, user.full_name,
                "⚠️ Yanıt Yok – Alarm Yükseltildi",
                f"'{alert['title']}' alarmına yanıt alınamadı. Otomatik olarak yükseltildi.",
                "escalation", alert["id"], "alert",
            )
        else:
            await repos.alerts.update(alert["id"], {
                "countdown_remaining_sec": remaining,
            })

    await db.commit()

# Tüm SELF kullanıcıları için simülasyon döngüsünü çalıştırır.
async def run_simulation_loop() -> None:
    logger.info("Simulation engine started.")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                repos = get_repos(db=db)
                result = await db.execute(
                    select(User).where(User.role == "SELF")
                )
                self_users = result.scalars().all()
                for user in self_users:
                    await _tick_user(db, repos, user)
        except Exception as exc:
            logger.exception("Simulation tick error: %s", exc)

        await asyncio.sleep(settings.SIMULATION_INTERVAL_SECONDS)
