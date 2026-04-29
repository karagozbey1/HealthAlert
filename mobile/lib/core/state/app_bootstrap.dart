import '../config/app_config.dart';
import '../models/anomaly_event.dart';
import '../models/enums.dart';
import '../models/history_item.dart';
import '../repositories/mock_repositories.dart';
import '../services/alert_state_machine.dart';
import '../services/api_client.dart';
import '../services/ble_device_service.dart';
import '../services/firestore_sync_service.dart';
import '../services/mock_demo_service.dart';
import '../services/recommendation_service.dart';
import '../services/transport_orchestrator.dart';
import 'app_controller.dart';

Future<AppController> buildAppController({
  bool demoMode = true,
  AppConfig? config,
}) async {
  final appConfig = config ?? (demoMode ? AppConfig.mockDefault : AppConfig.backendDefault);

  final historyRepository = MockHistoryRepository();
  await historyRepository.init();

  final anomalyRepository = MockAnomalyRepository(<AnomalyEvent>[]);

  if (demoMode) {
    final demo = MockDemoService();
    final anomalies = demo.initialAnomalies();
    for (final a in anomalies) {
      await anomalyRepository.addAnomaly(a);
    }

    if ((await historyRepository.getHistory()).isEmpty) {
      await historyRepository.addHistory(
        HistoryItem(
          id: 'seed1',
          type: HistoryItemType.alert,
          title: 'Kritik SpO2 Alarmı',
          subtitle: 'SpO2 %88\'e düştü. Acil kişiler bilgilendirildi.',
          timestamp: DateTime.now().subtract(const Duration(hours: 6)),
          severity: AlertSeverity.critical,
        ),
      );
      await historyRepository.addHistory(
        HistoryItem(
          id: 'seed2',
          type: HistoryItemType.status,
          title: 'İzleme Sürdürüldü',
          subtitle: 'Vital değerler normal aralığa döndü.',
          timestamp: DateTime.now().subtract(const Duration(hours: 5)),
          severity: AlertSeverity.normal,
        ),
      );
    }
  }

  ApiClient? apiClient;
  bool useBackend = !demoMode;

  if (!demoMode) {
    apiClient = ApiClient(baseUrl: appConfig.backendBaseUrl);
    final reachable = await apiClient.ping();
    if (!reachable) {
      useBackend = false;
      apiClient = null;
    }
  }

  final bleService = BleDeviceService();

  FirestoreSyncService? firestoreSync;
  if (appConfig.isFirebaseConfigured) {
    final firestoreOk = await initFirestoreSync(
      projectId: appConfig.firebaseProjectId,
    );
    if (firestoreOk) {
      firestoreSync = FirestoreSyncService(userId: '');
    }
  }

  final transportOrchestrator = TransportOrchestrator(
    bleService: bleService,
    apiClient: apiClient,
    transportMode: appConfig.transportMode,
  );

  return AppController(
    sessionRepository: MockSessionRepository(),
    userRepository: MockUserRepository(),
    alertRepository: MockAlertRepository(),
    anomalyRepository: anomalyRepository,
    historyRepository: historyRepository,
    settingsRepository: MockSettingsRepository(),
    deviceRepository: MockDeviceRepository(),
    contactRepository: MockContactRepository(),
    notificationRepository: MockNotificationRepository(),
    recommendationService: RecommendationService(),
    stateMachine: AlertStateMachine(),
    apiClient: apiClient,
    demoMode: !useBackend,
    backendUrl: appConfig.backendBaseUrl,
    transportMode: appConfig.transportMode,
    bleService: bleService,
    transportOrchestrator: transportOrchestrator,
    firestoreSync: firestoreSync,
  );
}

Future<AppController> buildMockAppController() => buildAppController(demoMode: true);
