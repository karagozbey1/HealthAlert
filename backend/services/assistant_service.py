from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Kullanıcı için LLM özet yanıtı üretir.
def generate_assistant_summary(
    live_status: Optional[Dict[str, Any]],
    recent_anomalies: List[Dict[str, Any]],
    recent_alerts: List[Dict[str, Any]],
    recent_history: List[Dict[str, Any]],
    role: str = "SELF",
) -> Dict[str, Any]:

    has_live = live_status is not None
    hr = live_status.get("heart_rate", 0) if has_live else None
    spo2 = live_status.get("spo2", 0) if has_live else None
    risk = live_status.get("risk_score", 0) if has_live else None
    motion = live_status.get("motion_score", 0) if has_live else None
    scenario = live_status.get("scenario", "unknown") if has_live else None

    summary_lines: List[str] = []
    recommendations: List[Dict[str, str]] = []
    reasoning: List[str] = []
    risk_level = "normal"
    confidence = "high" if has_live else "low"

    if not has_live:
        summary_lines.append("Yeterli canlı veri bulunmadığı için genel öneri gösteriliyor.")
        recommendations.append({
            "title": "Cihaz Bağlantısı",
            "action": "Sensörünüzü takın ve uygulamayı yenileyin.",
            "urgency": "info",
        })
        return _build_response(summary_lines, recommendations, reasoning, "unknown", confidence, role)

    if scenario == "critical" or (risk and risk > 0.8):
        risk_level = "critical"
        summary_lines.append("Kritik risk seviyesi tespit edildi.")
        reasoning.append(f"Risk skoru %{risk * 100:.0f} ile kritik eşiğin üzerinde.")
        recommendations.append({
            "title": "Acil Durum",
            "action": "Bulunduğunuz yerde kalın. Gerekiyorsa acil yardım isteyin.",
            "urgency": "critical",
        })
    elif scenario == "warning" or (risk and risk > 0.6):
        risk_level = "warning"
        summary_lines.append("Uyarı seviyesinde risk algılandı.")
        reasoning.append(f"Risk skoru %{risk * 100:.0f} ile uyarı bölgesinde.")
        recommendations.append({
            "title": "Dikkat",
            "action": "Oturun ve sakin olun. Vital değerlerinizi izleyin.",
            "urgency": "warning",
        })
    elif scenario in ("elevated_hr", "low_spo2") or (risk and risk > 0.3):
        risk_level = "watch"
        summary_lines.append("Bazı değerler izlem gerektiriyor.")
    else:
        risk_level = "normal"
        summary_lines.append("Genel durumunuz stabil görünüyor.")

    if hr:
        if hr > 130:
            summary_lines.append(f"Nabız {hr:.0f} bpm — çok yüksek.")
            reasoning.append("Nabız 130 bpm üzerinde, kritik bölgede.")
            recommendations.append({
                "title": "Yüksek Nabız",
                "action": "Dinlenin, derin nefes alın. Birkaç dakika içinde kontrol edin.",
                "urgency": "critical",
            })
        elif hr > 100:
            summary_lines.append(f"Nabız {hr:.0f} bpm — yüksek.")
            reasoning.append("Nabız normal üst sınırın (100 bpm) üzerinde.")
            recommendations.append({
                "title": "Yükselen Nabız",
                "action": "Fiziksel aktiviteyi azaltın, su için.",
                "urgency": "warning",
            })
        elif hr < 50:
            summary_lines.append(f"Nabız {hr:.0f} bpm — düşük.")
            reasoning.append("Nabız 50 bpm altında.")
            recommendations.append({
                "title": "Düşük Nabız",
                "action": "Dinlenin. Belirtiler devam ederse doktorunuza bildirin.",
                "urgency": "warning",
            })

    if spo2:
        if spo2 < 90:
            summary_lines.append(f"Oksijen doygunluğu %{spo2:.1f} — kritik.")
            reasoning.append("SpO2 %90 altında, acil müdahale gerekebilir.")
            recommendations.append({
                "title": "Kritik Oksijen",
                "action": "Oturarak dinlenin ve derin nefes alın. Doktorunuza derhal haber verin.",
                "urgency": "critical",
            })
        elif spo2 < 94:
            summary_lines.append(f"Oksijen doygunluğu %{spo2:.1f} — düşük.")
            reasoning.append("SpO2 normal alt sınırın (%94) altında.")
            recommendations.append({
                "title": "Düşük Oksijen",
                "action": "Oturarak dinlenin ve tekrar ölçüm bekleyin.",
                "urgency": "warning",
            })

    if motion and motion > 0.75:
        summary_lines.append("Hareket dengesizliği tespit edildi.")
        reasoning.append(f"Hareket skoru %{motion * 100:.0f} ile yüksek.")
        recommendations.append({
            "title": "Hareket Uyarısı",
            "action": "Ani hareketlerden kaçının. Oturmaya çalışın.",
            "urgency": "warning",
        })

    recent_anom_count = len(recent_anomalies)
    if recent_anom_count > 0:
        summary_lines.append(f"Son dönemde {recent_anom_count} anomali kaydedildi.")
        if recent_anom_count >= 3:
            reasoning.append("Tekrarlayan anomali örüntüsü dikkat gerektiriyor.")
            recommendations.append({
                "title": "Tekrarlayan Anomali",
                "action": "Doktorunuzla görüşmenizi öneririz.",
                "urgency": "info",
            })

    active_alerts = [a for a in recent_alerts if a.get("status") not in ("resolved", "closed", "acknowledged")]
    if active_alerts:
        summary_lines.append(f"{len(active_alerts)} aktif alarm mevcut.")

    if not recommendations:
        recommendations.append({
            "title": "Durum Stabil",
            "action": "Günlük takibe devam edin.",
            "urgency": "normal",
        })

    return _build_response(summary_lines, recommendations, reasoning, risk_level, confidence, role)

# Alarm için LLM açıklaması üretir.
def generate_alert_explanation(
    alert: Dict[str, Any],
    live_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    severity = alert.get("severity", "normal")
    title = alert.get("title", "Alarm")
    description = alert.get("description", "")
    status = alert.get("status", "unknown")

    explanation_lines = []
    actions = []

    explanation_lines.append(f"'{title}' alarmı tetiklendi.")
    if description:
        explanation_lines.append(f"Neden: {description}")

    if severity == "critical":
        explanation_lines.append("Bu alarm kritik seviyededir ve acil dikkat gerektirir.")
        actions.append("Bulunduğunuz yerde kalın ve gerekiyorsa acil yardım isteyin.")
        actions.append("Yakınlarınız otomatik olarak bilgilendirilmektedir.")
    elif severity == "warning":
        explanation_lines.append("Bu alarm uyarı seviyesindedir.")
        actions.append("Oturun ve sakin olun. Vital değerlerinizi izleyin.")
        actions.append("Belirtiler devam ederse yakınlarınıza haber verin.")
    else:
        explanation_lines.append("Bu alarm izleme seviyesindedir.")
        actions.append("Normal aktivitelerinize dikkatli devam edebilirsiniz.")

    status_labels = {
        "countdown": "Geri sayım devam ediyor — yanıt bekleniyor.",
        "acknowledged": "Kullanıcı durumu onayladı.",
        "escalated": "Acil yardım istendi.",
        "post_event_monitoring": "Olay sonrası izleme aktif.",
        "resolved": "Alarm çözüldü.",
        "closed": "Alarm kapatıldı.",
    }
    if status in status_labels:
        explanation_lines.append(status_labels[status])

    if live_status:
        hr = live_status.get("heart_rate")
        spo2 = live_status.get("spo2")
        if hr:
            explanation_lines.append(f"Güncel nabız: {hr:.0f} bpm")
        if spo2:
            explanation_lines.append(f"Güncel oksijen: %{spo2:.1f}")

    return {
        "explanation": " ".join(explanation_lines),
        "suggested_actions": actions,
        "severity": severity,
        "status": status,
        "disclaimer": "Bu bilgiler sensör verileri ve algoritmalar tarafından otomatik üretilmiştir. Kesin tıbbi teşhis yerine geçmez.",
    }

# Günlük sağlık özeti üretir.
def generate_daily_summary(
    live_status: Optional[Dict[str, Any]],
    anomalies_24h: List[Dict[str, Any]],
    alerts_24h: List[Dict[str, Any]],
    role: str = "SELF",
) -> Dict[str, Any]:

    total_anomalies = len(anomalies_24h)
    total_alerts = len(alerts_24h)
    critical_alerts = len([a for a in alerts_24h if a.get("severity") == "critical"])
    warning_alerts = len([a for a in alerts_24h if a.get("severity") == "warning"])

    lines = []

    if total_anomalies == 0 and total_alerts == 0:
        lines.append("Son 24 saatte herhangi bir anomali veya alarm kaydedilmedi.")
        lines.append("Genel durum stabil.")
        overall = "stabil"
    else:
        if critical_alerts > 0:
            lines.append(f"Son 24 saatte {critical_alerts} kritik alarm oluştu.")
            overall = "kritik"
        elif warning_alerts > 0:
            lines.append(f"Son 24 saatte {warning_alerts} uyarı seviyesinde alarm oluştu.")
            overall = "dikkat_gerektiren"
        else:
            overall = "stabil"

        if total_anomalies > 0:
            lines.append(f"Toplam {total_anomalies} anomali kaydedildi.")

        if critical_alerts > 0:
            last_critical = next(
                (a for a in alerts_24h if a.get("severity") == "critical"), None
            )
            if last_critical:
                lines.append(f"En dikkat çeken: {last_critical.get('title', 'Kritik alarm')}")

    if live_status is None:
        lines.append("Şu an aktif canlı veri bulunmuyor.")

    role_prefix = ""
    if role == "RELATIVE":
        role_prefix = "İzlediğiniz kişinin "
    elif role == "DOCTOR":
        role_prefix = "Hastanızın "

    return {
        "summary": f"{role_prefix}{' '.join(lines)}",
        "overall_status": overall,
        "anomaly_count": total_anomalies,
        "alert_count": total_alerts,
        "critical_count": critical_alerts,
        "warning_count": warning_alerts,
        "has_live_data": live_status is not None,
    }

def _build_response(
    summary_lines: List[str],
    recommendations: List[Dict[str, str]],
    reasoning: List[str],
    risk_level: str,
    confidence: str,
    role: str,
) -> Dict[str, Any]:

    role_prefix = ""
    if role == "RELATIVE":
        role_prefix = "İzlediğiniz kişi için: "
    elif role == "DOCTOR":
        role_prefix = "Hastanız için: "

    return {
        "summary": f"{role_prefix}{' '.join(summary_lines)}",
        "recommendations": recommendations,
        "reasoning": reasoning,
        "risk_level": risk_level,
        "confidence": confidence,
        "disclaimer": "Bu bilgiler sensör verileri ve algoritmalar tarafından otomatik üretilmiştir. Kesin tıbbi teşhis yerine geçmez.",
        "timestamp": datetime.utcnow().isoformat(),
    }
