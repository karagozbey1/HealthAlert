import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/models/alert_event.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/services/alert_state_machine.dart';

void main() {
  group('AlertStateMachine', () {
    final machine = AlertStateMachine();

    test('maps score to severity correctly', () {
      expect(machine.mapScoreToSeverity(0.10), AlertSeverity.normal);
      expect(machine.mapScoreToSeverity(0.40), AlertSeverity.watch);
      expect(machine.mapScoreToSeverity(0.70), AlertSeverity.warning);
      expect(machine.mapScoreToSeverity(0.90), AlertSeverity.critical);
    });

    test('countdown transitions to timedOut', () {
      final start = AlertEvent(
        id: 'a1',
        title: 'test',
        description: 'desc',
        severity: AlertSeverity.critical,
        status: AlertLifecycleStatus.countdown,
        createdAt: DateTime.now(),
        countdownTotalSec: 2,
        countdownRemainingSec: 1,
        recommendations: const [],
        relatedAnomalyId: null,
      );

      final next = machine.tick(start);
      expect(next.status, AlertLifecycleStatus.timedOut);
      expect(next.countdownRemainingSec, 0);
    });

    test('im-okay and emergency transitions', () {
      final start = AlertEvent(
        id: 'a2',
        title: 'test',
        description: 'desc',
        severity: AlertSeverity.warning,
        status: AlertLifecycleStatus.countdown,
        createdAt: DateTime.now(),
        countdownTotalSec: 20,
        countdownRemainingSec: 10,
        recommendations: const [],
        relatedAnomalyId: null,
      );

      final ok = machine.onImOkay(start);
      expect(ok.status, AlertLifecycleStatus.acknowledged);

      final em = machine.onEmergency(start);
      expect(em.status, AlertLifecycleStatus.emergencyRequested);
    });
  });
}
