import '../models/alert_event.dart';
import '../models/enums.dart';

/// Alarm yaşam döngüsünü geri sayım, yanıt ve kapanış adımlarıyla yönetir.
class AlertStateMachine {
  static const double _watchRiskThreshold = 0.30;
  static const double _warningRiskThreshold = 0.55;
  static const double _criticalRiskThreshold = 0.75;

  /// Sayısal risk skorunu alarm şiddeti seviyesine çevirir.
  AlertSeverity mapScoreToSeverity(double score) {
    if (score < _watchRiskThreshold) return AlertSeverity.normal;
    if (score < _warningRiskThreshold) return AlertSeverity.watch;
    if (score < _criticalRiskThreshold) return AlertSeverity.warning;
    return AlertSeverity.critical;
  }

  /// Yeni alarmı geri sayım durumuna alıp başlangıç süresini ayarlar.
  AlertEvent beginCountdown(AlertEvent event) {
    return event.copyWith(status: AlertLifecycleStatus.countdown);
  }

  /// Aktif alarm geri sayımını bir saniye azaltıp zaman aşımını işler.
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

  /// Kullanıcı iyi olduğunu bildirdiğinde alarm durumunu onaylandı yapar.
  AlertEvent onImOkay(AlertEvent event) {
    return event.copyWith(
      status: AlertLifecycleStatus.acknowledged,
      countdownRemainingSec: 0,
    );
  }

  /// Kullanıcı acil yardım istediğinde alarm durumunu yükseltir.
  AlertEvent onEmergency(AlertEvent event) {
    return event.copyWith(
      status: AlertLifecycleStatus.emergencyRequested,
      countdownRemainingSec: 0,
    );
  }

  /// Alarmı olay sonrası izleme durumuna geçirir.
  AlertEvent toPostEvent(AlertEvent event) {
    return event.copyWith(status: AlertLifecycleStatus.postEventMonitoring);
  }

  /// Alarm yaşam döngüsünü kapalı duruma taşır.
  AlertEvent close(AlertEvent event) {
    return event.copyWith(
      status: AlertLifecycleStatus.closed,
      countdownRemainingSec: 0,
    );
  }
}
