from __future__ import annotations

from datetime import datetime

from models import AlertEvent, HistoryItem
from uuid import uuid4

# Alarmı OKAY durumuna geçirir.
def transition_okay(alert: AlertEvent) -> AlertEvent:
    alert.status = "acknowledged"
    alert.countdown_remaining_sec = 0
    alert.resolved_at = datetime.utcnow()
    return alert

# Alarmı EMERGENCY durumuna geçirir.
def transition_emergency(alert: AlertEvent) -> AlertEvent:
    alert.status = "escalated"
    alert.countdown_remaining_sec = 0
    return alert

# Alarm sonrası izleme oturumu başlatır.
def transition_post_event(alert: AlertEvent) -> AlertEvent:
    alert.status = "post_event_monitoring"
    return alert

# Alarmı çözümlenmiş olarak kapatır.
def transition_resolved(alert: AlertEvent) -> AlertEvent:
    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()
    return alert

# Alarm olayından geçmiş kaydı oluşturur.
def make_history(alert: AlertEvent, outcome: str | None = None) -> HistoryItem:
    return HistoryItem(
        id=str(uuid4()),
        user_id=alert.user_id,
        item_type="alert",
        title=alert.title,
        subtitle=alert.description,
        severity=alert.severity,
        outcome=outcome,
    )
