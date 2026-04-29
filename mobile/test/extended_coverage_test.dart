// Additional test coverage for HealthAlert
// Categories: notifications read/unread, history creation, battery mode intervals,
// emergency flow, anomaly repository, user profile update, contacts, logout,
// severity mapping extended, settings serialization round-trip.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile/core/models/alert_event.dart';
import 'package:mobile/core/models/anomaly_event.dart';
import 'package:mobile/core/models/app_settings.dart';
import 'package:mobile/core/models/emergency_contact.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/models/history_item.dart';
import 'package:mobile/core/models/notification_item.dart';
import 'package:mobile/core/repositories/local_store.dart';
import 'package:mobile/core/repositories/mock_repositories.dart';
import 'package:mobile/core/services/alert_state_machine.dart';
import 'package:mobile/core/services/recommendation_service.dart';
import 'package:mobile/core/state/app_controller.dart';

// ---------------------------------------------------------------------------
// 1. Notifications — unread count and mark-all-read
// ---------------------------------------------------------------------------
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Notification unread/read tracking', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final hr = MockHistoryRepository();
      await hr.init();
      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: hr,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
      await controller.login('demo', 'pass');
    });

    test('anomaly creates unread notification', () async {
      await controller.simulateAnomaly(
        metric: 'SpO2', value: 89, unit: '%', score: 0.83,
      );
      expect(controller.unreadNotifications, greaterThan(0));
    });

    test('mark-all-read zeroes unread count', () async {
      await controller.simulateAnomaly(
        metric: 'SpO2', value: 89, unit: '%', score: 0.83,
      );
      expect(controller.unreadNotifications, greaterThan(0));
      await controller.markNotificationsRead();
      expect(controller.unreadNotifications, equals(0));
    });
  });

  // -------------------------------------------------------------------------
  // 2. History creation from anomaly
  // -------------------------------------------------------------------------
  group('History creation', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final hr = MockHistoryRepository();
      await hr.init();
      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: hr,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
      await controller.login('demo', 'pass');
    });

    test('anomaly with high score creates history entry', () async {
      expect(controller.history.isEmpty, true);
      await controller.simulateAnomaly(
        metric: 'Heart Rate', value: 142, unit: 'bpm', score: 0.88,
      );
      expect(controller.history.isNotEmpty, true);
    });

    test('history entries have non-empty titles', () async {
      await controller.simulateAnomaly(
        metric: 'Fall Risk', value: 0.91, unit: 'score', score: 0.91,
      );
      for (final item in controller.history) {
        expect(item.title.isNotEmpty, true);
      }
    });
  });

  // -------------------------------------------------------------------------
  // 3. Battery mode interval mapping
  // -------------------------------------------------------------------------
  group('Battery mode interval', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final hr = MockHistoryRepository();
      await hr.init();
      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: hr,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
      await controller.login('demo', 'pass');
    });

    test('saving battery mode saver updates settings', () async {
      final s = controller.settings.copyWith(batteryMode: BatteryMode.saver);
      await controller.saveSettings(s);
      expect(controller.settings.batteryMode, BatteryMode.saver);
    });

    test('saving battery mode performance updates settings', () async {
      final s = controller.settings.copyWith(batteryMode: BatteryMode.performance);
      await controller.saveSettings(s);
      expect(controller.settings.batteryMode, BatteryMode.performance);
    });
  });

  // -------------------------------------------------------------------------
  // 4. Emergency flow — request emergency, then close
  // -------------------------------------------------------------------------
  group('Emergency flow', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final hr = MockHistoryRepository();
      await hr.init();
      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: hr,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
      await controller.login('demo', 'pass');
    });

    test('request emergency transitions to post-event monitoring', () async {
      await controller.simulateAnomaly(
        metric: 'Fall Risk', value: 0.95, unit: 'score', score: 0.95,
      );
      expect(controller.activeAlert, isNotNull);

      await controller.requestEmergency();
      // requestEmergency transitions: countdown → emergencyRequested → postEventMonitoring
      expect(
        controller.activeAlert?.status,
        AlertLifecycleStatus.postEventMonitoring,
      );
    });

    test('close post-event after full lifecycle clears activeAlert', () async {
      await controller.simulateAnomaly(
        metric: 'SpO2', value: 87, unit: '%', score: 0.85,
      );
      await controller.confirmImOkay();
      await controller.closePostEvent();
      expect(controller.activeAlert, isNull);
    });
  });

  // -------------------------------------------------------------------------
  // 5. Anomaly repository stores and retrieves events
  // -------------------------------------------------------------------------
  group('Anomaly repository', () {
    test('stores anomaly events', () async {
      final repo = MockAnomalyRepository([]);
      final event = AnomalyEvent(
        id: 'an1',
        metric: 'Heart Rate',
        value: 132,
        unit: 'bpm',
        severity: AlertSeverity.warning,
        detectedAt: DateTime.now(),
        summary: 'Elevated HR',
      );
      await repo.addAnomaly(event);
      final all = await repo.getAnomalies();
      expect(all.length, 1);
      expect(all.first.metric, 'Heart Rate');
    });

    test('returns anomalies in reverse insertion order', () async {
      final repo = MockAnomalyRepository([]);
      for (var i = 0; i < 3; i++) {
        await repo.addAnomaly(AnomalyEvent(
          id: 'an$i',
          metric: 'Test',
          value: i.toDouble(),
          unit: 'bpm',
          severity: AlertSeverity.normal,
          detectedAt: DateTime.now(),
          summary: 'Test $i',
        ));
      }
      final all = await repo.getAnomalies();
      expect(all.first.id, 'an2');
    });
  });

  // -------------------------------------------------------------------------
  // 6. User profile update
  // -------------------------------------------------------------------------
  group('User profile', () {
    test('updateProfile persists new name', () async {
      final repo = MockUserRepository();
      final original = await repo.getProfile('u1');
      final updated = original.copyWith(fullName: 'New Name');
      await repo.updateProfile(updated);
      final reloaded = await repo.getProfile('u1');
      expect(reloaded.fullName, 'New Name');
    });
  });

  // -------------------------------------------------------------------------
  // 7. Emergency contacts
  // -------------------------------------------------------------------------
  group('Emergency contacts', () {
    test('contacts have at least one entry by default', () async {
      final repo = MockContactRepository();
      final contacts = await repo.getContacts();
      expect(contacts.isNotEmpty, true);
    });

    test('save contacts persists changes', () async {
      final repo = MockContactRepository();
      await repo.saveContacts([
        const EmergencyContact(
          id: 'c99',
          name: 'Test User',
          relation: 'Friend',
          phone: '05551234',
          isPrimary: true,
        ),
      ]);
      final reloaded = await repo.getContacts();
      expect(reloaded.length, 1);
      expect(reloaded.first.name, 'Test User');
    });
  });

  // -------------------------------------------------------------------------
  // 8. Logout clears session
  // -------------------------------------------------------------------------
  group('Logout', () {
    late AppController controller;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
      await LocalStore.clear();
      final hr = MockHistoryRepository();
      await hr.init();
      controller = AppController(
        sessionRepository: MockSessionRepository(),
        userRepository: MockUserRepository(),
        alertRepository: MockAlertRepository(),
        anomalyRepository: MockAnomalyRepository([]),
        historyRepository: hr,
        settingsRepository: MockSettingsRepository(),
        deviceRepository: MockDeviceRepository(),
        contactRepository: MockContactRepository(),
        notificationRepository: MockNotificationRepository(),
        recommendationService: RecommendationService(),
        stateMachine: AlertStateMachine(),
      );
      await controller.initialize();
    });

    test('after logout authenticated is false', () async {
      await controller.login('demo', 'pass');
      expect(controller.authenticated, true);
      await controller.logout();
      expect(controller.authenticated, false);
    });

    test('after logout user is null', () async {
      await controller.login('demo', 'pass');
      await controller.logout();
      expect(controller.user, isNull);
    });
  });

  // -------------------------------------------------------------------------
  // 9. Settings serialization round-trip
  // -------------------------------------------------------------------------
  group('Settings serialization', () {
    test('toJson / fromJson round-trip preserves all fields', () {
      const original = AppSettings(
        hrHighThreshold: 140,
        hrLowThreshold: 45,
        notificationsEnabled: false,
        batteryMode: BatteryMode.saver,
        dimBrightness: true,
        backgroundMonitoring: false,
        uploadIntervalMinutes: 10,
      );

      final json = original.toJson();
      final restored = AppSettings.fromJson(json);

      expect(restored.hrHighThreshold, original.hrHighThreshold);
      expect(restored.hrLowThreshold, original.hrLowThreshold);
      expect(restored.notificationsEnabled, original.notificationsEnabled);
      expect(restored.batteryMode, original.batteryMode);
      expect(restored.dimBrightness, original.dimBrightness);
      expect(restored.backgroundMonitoring, original.backgroundMonitoring);
      expect(restored.uploadIntervalMinutes, original.uploadIntervalMinutes);
    });

    test('copyWith changes only specified field', () {
      const original = AppSettings.defaults;
      final modified = original.copyWith(notificationsEnabled: false);
      expect(modified.notificationsEnabled, false);
      expect(modified.hrHighThreshold, original.hrHighThreshold);
      expect(modified.batteryMode, original.batteryMode);
    });
  });

  // -------------------------------------------------------------------------
  // 10. AlertStateMachine — all severity thresholds
  // -------------------------------------------------------------------------
  group('AlertStateMachine severity thresholds', () {
    final machine = AlertStateMachine();

    test('score 0.0 maps to normal', () {
      expect(machine.mapScoreToSeverity(0.0), AlertSeverity.normal);
    });

    test('score 0.25 maps to normal', () {
      expect(machine.mapScoreToSeverity(0.25), AlertSeverity.normal);
    });

    test('score 0.30 maps to watch', () {
      expect(machine.mapScoreToSeverity(0.30), AlertSeverity.watch);
    });

    test('score 0.55 maps to warning', () {
      expect(machine.mapScoreToSeverity(0.55), AlertSeverity.warning);
    });

    test('score 0.60 maps to warning', () {
      expect(machine.mapScoreToSeverity(0.60), AlertSeverity.warning);
    });

    test('score 0.74 maps to warning', () {
      expect(machine.mapScoreToSeverity(0.74), AlertSeverity.warning);
    });

    test('score 0.75 maps to critical', () {
      expect(machine.mapScoreToSeverity(0.75), AlertSeverity.critical);
    });

    test('score 1.0 maps to critical', () {
      expect(machine.mapScoreToSeverity(1.0), AlertSeverity.critical);
    });

    test('post-event close → closed status', () {
      final alert = AlertEvent(
        id: 'x1',
        title: 'test',
        description: 'desc',
        severity: AlertSeverity.warning,
        status: AlertLifecycleStatus.postEventMonitoring,
        createdAt: DateTime.now(),
        countdownTotalSec: 30,
        countdownRemainingSec: 0,
        recommendations: const [],
        relatedAnomalyId: null,
      );
      final closed = machine.close(alert);
      expect(closed.status, AlertLifecycleStatus.closed);
    });
  });

  // -------------------------------------------------------------------------
  // 11. HistoryItem serialization
  // -------------------------------------------------------------------------
  group('HistoryItem serialization', () {
    test('toJson / fromJson round-trip', () {
      final original = HistoryItem(
        id: 'h1',
        type: HistoryItemType.alert,
        title: 'Test Alert',
        subtitle: 'Test subtitle',
        timestamp: DateTime.utc(2024, 1, 15, 10, 30),
        severity: AlertSeverity.warning,
      );

      final restored = HistoryItem.fromJson(original.toJson());
      expect(restored.id, original.id);
      expect(restored.type, original.type);
      expect(restored.title, original.title);
      expect(restored.subtitle, original.subtitle);
      expect(restored.severity, original.severity);
      expect(restored.timestamp, original.timestamp);
    });
  });

  // -------------------------------------------------------------------------
  // 12. NotificationItem
  // -------------------------------------------------------------------------
  group('NotificationItem', () {
    test('copyWith sets read flag', () {
      final item = NotificationItem(
        id: 'n1',
        title: 'Alert',
        body: 'Something happened',
        channel: NotificationChannel.inApp,
        createdAt: DateTime.now(),
        read: false,
      );
      final readItem = item.copyWith(read: true);
      expect(readItem.read, true);
      expect(readItem.id, 'n1');
    });
  });
}
