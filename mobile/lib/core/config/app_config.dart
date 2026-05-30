import '../models/enums.dart';

const _kDefaultBackendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'http://localhost:8000',
);

const _kFirebaseProjectId = String.fromEnvironment(
  'FIREBASE_PROJECT_ID',
  defaultValue: '',
);

const _kTransportMode = String.fromEnvironment(
  'TRANSPORT_MODE',
  defaultValue: 'auto',
);

/// Mobil uygulamanın backend ve demo çalışma ayarlarını tutar.
class AppConfig {
  const AppConfig({
    required this.environment,
    required this.useFirebaseAdapters,
    this.backendBaseUrl = _kDefaultBackendUrl,
    this.demoMode = false,
    this.firebaseProjectId = _kFirebaseProjectId,
    this.transportMode = _kTransportMode,
  });

  final AppEnvironment environment;
  final bool useFirebaseAdapters;

  final String backendBaseUrl;

  final bool demoMode;

  final String firebaseProjectId;

  final String transportMode;

  bool get isFirebaseConfigured => firebaseProjectId.isNotEmpty;

  static const AppConfig mockDefault = AppConfig(
    environment: AppEnvironment.mock,
    useFirebaseAdapters: false,
    demoMode: true,
    transportMode: 'auto',
  );

  static const AppConfig backendDefault = AppConfig(
    environment: AppEnvironment.mock,
    useFirebaseAdapters: false,
    backendBaseUrl: _kDefaultBackendUrl,
    demoMode: false,
    firebaseProjectId: 'healthalertsystem-2776a',
  );

  static const AppConfig production = AppConfig(
    environment: AppEnvironment.firebase,
    useFirebaseAdapters: true,
    backendBaseUrl: _kDefaultBackendUrl,
    demoMode: false,
    firebaseProjectId: 'healthalertsystem-2776a',
    transportMode: 'auto',
  );
}
