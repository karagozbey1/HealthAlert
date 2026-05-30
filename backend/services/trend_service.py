from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Geçmiş verileri analiz ederek trend raporu döndürür.
def analyze_trends(
    history_items: List[Dict[str, Any]],
    anomalies: List[Dict[str, Any]],
    live_status: Optional[Dict[str, Any]] = None,
    role: str = "SELF",
) -> Dict[str, Any]:

    """trend servisindeki HealthAlert iş kuralını uygular."""
    now = datetime.utcnow()
    last_1h = now - timedelta(hours=1)
    last_24h = now - timedelta(hours=24)

    anomalies_1h = [a for a in anomalies if _parse_dt(a.get("detected_at") or a.get("created_at")) >= last_1h]
    anomalies_24h = [a for a in anomalies if _parse_dt(a.get("detected_at") or a.get("created_at")) >= last_24h]

    alerts_in_history = [h for h in history_items if h.get("item_type") == "alert"]
    alerts_1h = [h for h in alerts_in_history if _parse_dt(h.get("created_at")) >= last_1h]
    alerts_24h = [h for h in alerts_in_history if _parse_dt(h.get("created_at")) >= last_24h]

    metric_counts: Dict[str, int] = {}
    for a in anomalies_24h:
        m = a.get("metric", "unknown")
        metric_counts[m] = metric_counts.get(m, 0) + 1

    recurring_metrics = {k: v for k, v in metric_counts.items() if v >= 2}

    trend_label = _determine_trend_label(anomalies_1h, anomalies_24h, alerts_1h, live_status)

    summary_lines = _build_trend_summary(
        trend_label, anomalies_1h, anomalies_24h, alerts_24h,
        recurring_metrics, live_status, role,
    )

    top_concern = None
    if anomalies_1h:
        last_anom = anomalies_1h[-1]
        top_concern = last_anom.get("summary") or f"{last_anom.get('metric', 'Bilinmeyen')} anomalisi"

    return {
        "trend_label": trend_label,
        "summary": " ".join(summary_lines),
        "anomalies_last_1h": len(anomalies_1h),
        "anomalies_last_24h": len(anomalies_24h),
        "alerts_last_1h": len(alerts_1h),
        "alerts_last_24h": len(alerts_24h),
        "recurring_metrics": recurring_metrics,
        "top_concern": top_concern,
        "has_sufficient_data": len(history_items) >= 3 or live_status is not None,
        "timestamp": now.isoformat(),
    }

# Son veri yogunluguna gore genel trend etiketini secer.
def _determine_trend_label(
    anomalies_1h: List[Dict],
    anomalies_24h: List[Dict],
    alerts_1h: List[Dict],
    live_status: Optional[Dict],
) -> str:

    """trend servisindeki HealthAlert iş kuralını uygular."""
    if live_status is None and not anomalies_24h:
        return "veri_yetersiz"

    if len(anomalies_1h) >= 2 or len(alerts_1h) >= 1:
        return "artan_risk"

    if len(anomalies_24h) > 0 and len(anomalies_1h) == 0:
        return "iyilesiyor"

    if live_status:
        risk = live_status.get("risk_score", 0)
        if risk < 0.3:
            return "stabil"
        elif risk < 0.6:
            return "izlem_gerektiren"
        else:
            return "artan_risk"

    return "stabil"

TREND_LABELS_TR = {
    "artan_risk": "Artan Risk",
    "stabil": "Stabil",
    "iyilesiyor": "İyileşiyor",
    "izlem_gerektiren": "İzlem Gerektiren",
    "olcum_kalitesi_dusuk": "Ölçüm Kalitesi Düşük",
    "veri_yetersiz": "Veri Yetersiz",
}

# Trend etiketini destekleyen aciklayici cumleleri olusturur.
def _build_trend_summary(
    trend_label: str,
    anomalies_1h: List[Dict],
    anomalies_24h: List[Dict],
    alerts_24h: List[Dict],
    recurring_metrics: Dict[str, int],
    live_status: Optional[Dict],
    role: str,
) -> List[str]:

    """trend servisinde kullanılacak kayıt veya bağlamı hazırlar."""
    lines = []
    role_prefix = ""
    if role == "RELATIVE":
        role_prefix = "İzlediğiniz kişinin "
    elif role == "DOCTOR":
        role_prefix = "Hastanızın "

    label_tr = TREND_LABELS_TR.get(trend_label, trend_label)

    if trend_label == "veri_yetersiz":
        lines.append(f"{role_prefix}Trend analizi için yeterli veri bulunmuyor.")
        return lines

    lines.append(f"{role_prefix}Genel trend: {label_tr}.")

    if trend_label == "artan_risk":
        lines.append(f"Son 1 saatte {len(anomalies_1h)} anomali kaydedildi.")
        if live_status:
            risk = live_status.get("risk_score", 0)
            lines.append(f"Güncel risk skoru: %{risk * 100:.0f}.")
    elif trend_label == "iyilesiyor":
        lines.append("Son 1 saatte yeni anomali kaydedilmedi.")
        if anomalies_24h:
            lines.append(f"Son 24 saatteki toplam anomali: {len(anomalies_24h)}.")
    elif trend_label == "stabil":
        lines.append("Değerler normal aralıkta seyrediyor.")

    if recurring_metrics:
        for metric, count in recurring_metrics.items():
            lines.append(f"{metric}: son 24 saatte {count} kez tekrarladı.")

    if alerts_24h:
        lines.append(f"Son 24 saatte {len(alerts_24h)} alarm kaydı mevcut.")

    return lines

# Kayittaki farkli tarih alanlarini tek bir datetime nesnesine cevirir.
def _parse_dt(val) -> datetime:
    """trend servisindeki HealthAlert iş kuralını uygular."""
    if val is None:
        return datetime.min
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        return datetime.min
