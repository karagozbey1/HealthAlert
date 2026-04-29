import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/repositories/local_store.dart';
import 'package:mobile/core/repositories/mock_repositories.dart';
import 'package:mobile/core/services/alert_state_machine.dart';
import 'package:mobile/core/services/recommendation_service.dart';
import 'package:mobile/core/state/app_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppController flows', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final historyRepo = MockHistoryRepository();
      await historyRepo.init();

      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: historyRepo,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
    });

    test('mock login persists authenticated session', () async {
      expect(controller.authenticated, false);
      final ok = await controller.login('demo', 'pass');
      expect(ok, true);
      expect(controller.authenticated, true);
      expect(controller.user, isNotNull);
    });

    test('warning anomaly raises alert and notification', () async {
      await controller.login('demo', 'pass');

      await controller.simulateAnomaly(
        metric: 'Heart Rate',
        value: 128,
        unit: 'bpm',
        score: 0.79,
      );

      expect(controller.activeAlert, isNotNull);
      expect(controller.activeAlert!.severity, AlertSeverity.critical);
      expect(controller.notifications.isNotEmpty, true);
      expect(controller.history.isNotEmpty, true);
    });

    test('im-okay moves event to post-event state', () async {
      await controller.login('demo', 'pass');
      await controller.simulateAnomaly(
        metric: 'SpO2',
        value: 88,
        unit: '%',
        score: 0.8,
      );

      await controller.confirmImOkay();
      expect(controller.activeAlert, isNotNull);
      expect(
        controller.activeAlert!.status,
        AlertLifecycleStatus.postEventMonitoring,
      );
    });

    test('close post-event clears active alert', () async {
      await controller.login('demo', 'pass');
      await controller.simulateAnomaly(
        metric: 'SpO2',
        value: 88,
        unit: '%',
        score: 0.8,
      );
      await controller.confirmImOkay();
      await controller.closePostEvent();
      expect(controller.activeAlert, isNull);
    });
  });
}
