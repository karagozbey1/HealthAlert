import '../models/alert_event.dart';
import '../models/enums.dart';

class AlertStateMachine {
  AlertSeverity mapScoreToSeverity(double score) {
    if (score < 0.30) return AlertSeverity.normal;
    if (score < 0.55) return AlertSeverity.watch;
    if (score < 0.75) return AlertSeverity.warning;
    return AlertSeverity.critical;
  }

  AlertEvent beginCountdown(AlertEvent event) {
    return event.copyWith(status: AlertLifecycleStatus.countdown);
  }

  AlertEvent tick(AlertEvent event) {
    if (event.countdownRemainingSec <= 0) {
      return event.copyWith(
        status: AlertLifecycleStatus.timedOut,
        countdownRemainingSec: 0,
      );
    }

    final next = event.countdownRemainingSec - 1;
    if (next <= 0) {
      return event.copyWith(
        status: AlertLifecycleStatus.timedOut,
        countdownRemainingSec: 0,
      );
    }

    return event.copyWith(
      status: AlertLifecycleStatus.countdown,
      countdownRemainingSec: next,
    );
  }

  AlertEvent onImOkay(AlertEvent event) {
    return event.copyWith(
      status: AlertLifecycleStatus.acknowledged,
      countdownRemainingSec: 0,
    );
  }

  AlertEvent onEmergency(AlertEvent event) {
    return event.copyWith(
      status: AlertLifecycleStatus.emergencyRequested,
      countdownRemainingSec: 0,
    );
  }

  AlertEvent toPostEvent(AlertEvent event) {
    return event.copyWith(status: AlertLifecycleStatus.postEventMonitoring);
  }

  AlertEvent close(AlertEvent event) {
    return event.copyWith(status: AlertLifecycleStatus.closed, countdownRemainingSec: 0);
  }
}
