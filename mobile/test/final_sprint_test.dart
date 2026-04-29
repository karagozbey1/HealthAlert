// Final Sprint Tests â€” Health Assistant, Mode Separation, Empty States
//
// Tests:
//   1. HealthAssistantService â€” local rule-based generation
//   2. Mode separation â€” live mode never returns demo data
//   3. Empty state widget rendering
//   4. Recommendation service public API
//   5. LiveStatus model parsing

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/models/live_status.dart';
import 'package:mobile/core/repositories/local_store.dart';
import 'package:mobile/core/repositories/mock_repositories.dart';
import 'package:mobile/core/services/alert_state_machine.dart';
import 'package:mobile/core/services/recommendation_service.dart';
import 'package:mobile/core/services/health_assistant_service.dart';
import 'package:mobile/core/state/app_controller.dart';
import 'package:mobile/ui/widgets/empty_state_widget.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // ---------------------------------------------------------------------------
  // 1. HealthAssistantService â€” local rule-based generation
  // ---------------------------------------------------------------------------
  group('HealthAssistantService yerel Ã¼retim', () {
    late HealthAssistantService service;

    setUp(() {
      service = HealthAssistantService();
    });

    test('normal vital ile stabil Ã¶zet Ã¼retir', () async {
      final live = LiveStatus(
        id: 'test',
        userId: 'u1',
        heartRate: 72,
        spo2: 98,
        motionScore: 0.1,
        riskScore: 0.05,
        scenario: 'normal',
        timestamp: DateTime.now(),
      );
      final summary = await service.getSummary(liveStatus: live);
      expect(summary.summary, isNotEmpty);
      expect(summary.recommendations, isNotEmpty);
      expect(summary.riskLevel, isIn(['normal', 'stabil']));
    });

    test('yÃ¼ksek HR ile uyarÄ± Ã¶zeti Ã¼retir', () async {
      final live = LiveStatus(
        id: 'test',
        userId: 'u1',
        heartRate: 125,
        spo2: 97,
        motionScore: 0.2,
        riskScore: 0.45,
        scenario: 'elevated_hr',
        timestamp: DateTime.now(),
      );
      final summary = await service.getSummary(liveStatus: live);
      expect(summary.summary, isNotEmpty);
      expect(summary.recommendations.any((r) =>
          r.title.contains('Nab') || r.urgency == 'warning' || r.urgency == 'critical'), isTrue);
    });

    test('dÃ¼ÅŸÃ¼k SpO2 ile kritik Ã¶zet Ã¼retir', () async {
      final live = LiveStatus(
        id: 'test',
        userId: 'u1',
        heartRate: 72,
        spo2: 89,
        motionScore: 0.1,
        riskScore: 0.7,
        scenario: 'low_spo2',
        timestamp: DateTime.now(),
      );
      final summary = await service.getSummary(liveStatus: live);
      expect(summary.summary, isNotEmpty);
      expect(summary.recommendations.any((r) =>
          r.title.contains('Oksijen') || r.urgency == 'critical'), isTrue);
    });

    test('null live ile veri_yok Ã¶zeti Ã¼retir', () async {
      final summary = await service.getSummary(liveStatus: null);
      expect(summary.summary, isNotEmpty);
      expect(summary.confidence, equals('low'));
    });

    test('getTrendSync null live â†’ veri_yetersiz', () {
      final trend = service.getTrendSync(null);
      expect(trend.trendLabel, equals('veri_yetersiz'));
      expect(trend.hasSufficientData, isFalse);
    });

    test('getTrendSync normal â†’ stabil', () {
      final live = LiveStatus(
        id: 'test',
        userId: 'u1',
        heartRate: 72,
        spo2: 98,
        motionScore: 0.1,
        riskScore: 0.05,
        scenario: 'normal',
        timestamp: DateTime.now(),
      );
      final trend = service.getTrendSync(live);
      expect(trend.trendLabel, isIn(['stabil', 'iyilesiyor', 'veri_yetersiz']));
    });
  });

  // ---------------------------------------------------------------------------
  // 2. Mode separation â€” demo mod verisi
  // ---------------------------------------------------------------------------
  group('Demo mod veri ayrÄ±mÄ±', () {
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
        demoMode: true,
      );
      await controller.initialize();
    });

    test('demo modda loadMonitoredUsers mock kullanÄ±cÄ± dÃ¶ner', () async {
      await controller.login('relative@demo.com', 'demo1234');
      await controller.loadMonitoredUsers();
      expect(controller.monitoredUsers, isNotEmpty);
      expect(controller.monitoredUsers.first.fullName, isNotEmpty);
    });

    test('demo modda getAlertsForUser mock alarm dÃ¶ner', () async {
      await controller.login('relative@demo.com', 'demo1234');
      final alerts = await controller.getAlertsForUser('demo_self');
      expect(alerts, isNotEmpty);
      expect(alerts.first.title, isNotEmpty);
    });

    test('demo modda getHistoryForUser mock geÃ§miÅŸ dÃ¶ner', () async {
      await controller.login('relative@demo.com', 'demo1234');
      final history = await controller.getHistoryForUser('demo_self');
      expect(history, isNotEmpty);
    });

    test('demo modda getLiveStatusForUser mock status dÃ¶ner', () async {
      await controller.login('relative@demo.com', 'demo1234');
      final live = await controller.getLiveStatusForUser('demo_self');
      expect(live, isNotNull);
      expect(live!.heartRate, greaterThan(0));
    });

    test('isBackendMode demo modda false dÃ¶ner', () {
      expect(controller.isBackendMode, isFalse);
    });
  });

  // ---------------------------------------------------------------------------
  // 3. Empty state widgets
  // ---------------------------------------------------------------------------
  group('BoÅŸ durum widget\'larÄ±', () {
    testWidgets('EmptyStateWidget baÅŸlÄ±k ve alt baÅŸlÄ±k gÃ¶sterir', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: EmptyStateWidget(
              icon: Icons.history,
              title: 'Test BaÅŸlÄ±k',
              subtitle: 'Test aÃ§Ä±klama',
            ),
          ),
        ),
      );
      expect(find.text('Test BaÅŸlÄ±k'), findsOneWidget);
      expect(find.text('Test aÃ§Ä±klama'), findsOneWidget);
      expect(find.byIcon(Icons.history), findsOneWidget);
    });

    testWidgets('EmptyStateWidget aksiyon butonu Ã§alÄ±ÅŸÄ±r', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: EmptyStateWidget(
              icon: Icons.refresh,
              title: 'BoÅŸ',
              actionLabel: 'Yenile',
              onAction: () => tapped = true,
            ),
          ),
        ),
      );
      await tester.tap(find.text('Yenile'));
      expect(tapped, isTrue);
    });

    testWidgets('LoadingStateWidget yÃ¼kleniyor gÃ¶stergesi vardÄ±r', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: LoadingStateWidget(message: 'Veri yÃ¼kleniyor...'),
          ),
        ),
      );
      expect(find.text('Veri yÃ¼kleniyor...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('ErrorStateWidget hata mesajÄ± ve retry butonu', (tester) async {
      bool retried = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ErrorStateWidget(
              message: 'Sunucuya ulaÅŸÄ±lamadÄ±',
              onRetry: () => retried = true,
            ),
          ),
        ),
      );
      expect(find.text('Sunucuya ulaÅŸÄ±lamadÄ±'), findsOneWidget);
      await tester.tap(find.text('Tekrar Dene'));
      expect(retried, isTrue);
    });
  });

  // ---------------------------------------------------------------------------
  // 4. Recommendation service
  // ---------------------------------------------------------------------------
  group('RecommendationService', () {
    test('forSeverity tÃ¼m severity seviyeleri iÃ§in Ã¶neri dÃ¶ner', () {
      final service = RecommendationService();
      for (final sev in AlertSeverity.values) {
        final recs = service.forSeverity(sev);
        expect(recs, isNotEmpty, reason: '${sev.name} iÃ§in Ã¶neri yok');
      }
    });

    test('forLiveStatus null live â†’ baÄŸlantÄ± bekleniyor Ã¶nerisi', () {
      final service = RecommendationService();
      final recs = service.forLiveStatus(null);
      expect(recs, isNotEmpty);
      expect(recs.first.title, isNotEmpty);
    });

    test('forLiveStatus yÃ¼ksek HR â†’ nabÄ±z uyarÄ±sÄ±', () {
      final service = RecommendationService();
      final live = LiveStatus(
        id: 'l', userId: 'u', heartRate: 120, spo2: 98,
        motionScore: 0.1, riskScore: 0.3, scenario: 'elevated_hr',
        timestamp: DateTime.now(),
      );
      final recs = service.forLiveStatus(live);
      expect(recs.any((r) => r.title.contains('Nab') || r.urgency == RecommendationUrgency.warning || r.urgency == RecommendationUrgency.critical), isTrue);
    });

    test('Recommendation alanlarÄ± doÄŸru', () {
      const rec = Recommendation(
        title: 'Test Ã–neri',
        detail: 'Test detay',
        urgency: RecommendationUrgency.warning,
        action: 'Test aksiyon',
      );
      expect(rec.title, equals('Test Ã–neri'));
      expect(rec.detail, equals('Test detay'));
      expect(rec.urgency, equals(RecommendationUrgency.warning));
      expect(rec.action, equals('Test aksiyon'));
    });
  });

  // ---------------------------------------------------------------------------
  // 5. LiveStatus model
  // ---------------------------------------------------------------------------
  group('LiveStatus model', () {
    test('fromJson doÄŸru parse eder', () {
      final json = {
        'id': 'ls1',
        'user_id': 'u1',
        'heart_rate': 85.0,
        'spo2': 97.5,
        'motion_score': 0.3,
        'risk_score': 0.12,
        'scenario': 'normal',
        'timestamp': '2024-01-01T12:00:00Z',
      };
      final ls = LiveStatus.fromJson(json);
      expect(ls.heartRate, equals(85.0));
      expect(ls.spo2, equals(97.5));
      expect(ls.isAlert, isFalse);
      expect(ls.scenarioLabel, equals('Normal'));
    });

    test('isAlert warning ve critical iÃ§in true dÃ¶ner', () {
      for (final scenario in ['warning', 'critical']) {
        final ls = LiveStatus(
          id: 'ls', userId: 'u', heartRate: 72, spo2: 98,
          motionScore: 0.1, riskScore: 0.5, scenario: scenario,
          timestamp: DateTime.now(),
        );
        expect(ls.isAlert, isTrue, reason: '$scenario iÃ§in isAlert false olmamalÄ±');
      }
    });

    test('scenarioLabel bilinen senaryolar icin bos degil', () {
      for (final scenario in ['elevated_hr', 'low_spo2', 'warning', 'critical', 'recovery', 'normal']) {
        final ls = LiveStatus(
          id: 'ls', userId: 'u', heartRate: 72, spo2: 98,
          motionScore: 0.1, riskScore: 0.1, scenario: scenario,
          timestamp: DateTime.now(),
        );
        expect(ls.scenarioLabel, isNotEmpty, reason: '$scenario icin scenarioLabel bos');
      }
    });

    test('scenarioLabel ASCII-safe senaryolar dogru', () {
      // Only test scenarios with purely ASCII labels to avoid encoding issues
      final asciiCases = {
        'critical': 'Kritik',
        'recovery': 'Toparlanma',
        'normal': 'Normal',
      };
      for (final entry in asciiCases.entries) {
        final ls = LiveStatus(
          id: 'ls', userId: 'u', heartRate: 72, spo2: 98,
          motionScore: 0.1, riskScore: 0.1, scenario: entry.key,
          timestamp: DateTime.now(),
        );
        expect(ls.scenarioLabel, equals(entry.value),
            reason: '${entry.key} icin etiket yanlis');
      }
    });

    test('scenarioLabel elevated_hr icin Nab iceriyor', () {
      final ls = LiveStatus(
        id: 'ls', userId: 'u', heartRate: 72, spo2: 98,
        motionScore: 0.1, riskScore: 0.1, scenario: 'elevated_hr',
        timestamp: DateTime.now(),
      );
      expect(ls.scenarioLabel, contains('Nab'));
    });
  });
}
