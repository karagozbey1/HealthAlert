import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../models/alert_event.dart';
import '../models/anomaly_event.dart';
import '../models/app_settings.dart';
import '../models/clinical_note.dart';
import '../models/device_state.dart';
import '../models/emergency_contact.dart';
import '../models/enums.dart';
import '../models/history_item.dart';
import '../models/link_code.dart';
import '../models/live_status.dart';
import '../models/notification_item.dart';
import '../models/user_profile.dart';
import '../models/user_relation.dart';
import '../repositories/local_store.dart';
import '../repositories/repository_interfaces.dart';
import '../services/alert_state_machine.dart';
import '../services/api_client.dart';
import '../services/ble_device_service.dart';
import '../services/firestore_sync_service.dart';
import '../services/live_data_service.dart';
import '../services/recommendation_service.dart';
import '../services/transport_orchestrator.dart';

class AppController extends ChangeNotifier {
  AppController({
    required SessionRepository sessionRepository,
    required UserRepository userRepository,
    required AlertRepository alertRepository,
    required AnomalyRepository anomalyRepository,
    required HistoryRepository historyRepository,
    required SettingsRepository settingsRepository,
    required DeviceRepository deviceRepository,
    required ContactRepository contactRepository,
    required NotificationRepository notificationRepository,
    required RecommendationService recommendationService,
    required AlertStateMachine stateMachine,
    ApiClient? apiClient,
    bool demoMode = true,
    String backendUrl = 'http://localhost:8000',
    String transportMode = 'auto',
    BleDeviceService? bleService,
    TransportOrchestrator? transportOrchestrator,
    FirestoreSyncService? firestoreSync,
  })  : _sessionRepository = sessionRepository,
        _userRepository = userRepository,
        _alertRepository = alertRepository,
        _anomalyRepository = anomalyRepository,
        _historyRepository = historyRepository,
        _settingsRepository = settingsRepository,
        _deviceRepository = deviceRepository,
        _contactRepository = contactRepository,
        _notificationRepository = notificationRepository,
        _recommendationService = recommendationService,
        _stateMachine = stateMachine,
        _apiClient = apiClient,
        _demoMode = demoMode,
        _backendUrl = backendUrl,
        _transportMode = transportMode,
        _bleService = bleService ?? BleDeviceService(),
        _transportOrchestrator = transportOrchestrator,
        _firestoreSync = firestoreSync;

  final SessionRepository _sessionRepository;
  final UserRepository _userRepository;
  final AlertRepository _alertRepository;
  final AnomalyRepository _anomalyRepository;
  final HistoryRepository _historyRepository;
  final SettingsRepository _settingsRepository;
  final DeviceRepository _deviceRepository;
  final ContactRepository _contactRepository;
  final NotificationRepository _notificationRepository;
  final RecommendationService _recommendationService;
  final AlertStateMachine _stateMachine;
  ApiClient? _apiClient;
  bool _demoMode;
  String _backendUrl = 'http://localhost:8000';
  final String _transportMode;

  final BleDeviceService _bleService;
  TransportOrchestrator? _transportOrchestrator;
  FirestoreSyncService? _firestoreSync;
  StreamSubscription<BlePacket>? _transportPacketSub;
  StreamSubscription<LiveStatus>? _transportStatusSub;

  bool _initialized = false;
  bool _authenticated = false;
  bool _isRefreshing = false;
  UserProfile? _user;
  String? _authToken;
  AppSettings _settings = AppSettings.defaults;
  DeviceState _deviceState = DeviceState(
    batteryPercent: 92,
    isConnected: true,
    mode: BatteryMode.balanced,
    lastSync: DateTime.now(),
  );
  List<AnomalyEvent> _anomalies = const [];
  List<HistoryItem> _history = const [];
  List<EmergencyContact> _contacts = const [];
  List<NotificationItem> _notifications = const [];
  AlertEvent? _activeAlert;

  List<UserRelation> _relations = const [];
  List<LinkCode> _linkCodes = const [];
  LiveStatus? _latestLiveStatus;

  List<UserProfile> _monitoredUsers = const [];
  final Map<String, LiveStatus> _monitoredLiveStatuses = {};
  final Map<String, List<AlertEvent>> _monitoredAlerts = {};

  final Map<String, List<ClinicalNote>> _clinicalNotes = {};

  Timer? _alertTimer;
  LiveDataService? _liveDataService;
  Timer? _monitoredLiveTimer;
  bool _monitoredLiveRefreshing = false;

  bool get initialized => _initialized;
  bool get authenticated => _authenticated;
  UserProfile? get user => _user;
  UserRole get role => _user?.role ?? UserRole.self;
  AppSettings get settings => _settings;
  DeviceState get deviceState => _deviceState;
  List<AnomalyEvent> get anomalies => _anomalies;
  List<HistoryItem> get history => _history;
  List<EmergencyContact> get contacts => _contacts;
  List<NotificationItem> get notifications => _notifications;
  AlertEvent? get activeAlert => _activeAlert;
  int get unreadNotifications => _notifications.where((n) => !n.read).length;

  List<UserRelation> get relations => _relations;
  List<LinkCode> get linkCodes => _linkCodes;
  LiveStatus? get latestLiveStatus => _latestLiveStatus;
  List<UserProfile> get monitoredUsers => _monitoredUsers;
  Map<String, LiveStatus> get monitoredLiveStatuses => _monitoredLiveStatuses;
  Map<String, List<AlertEvent>> get monitoredAlerts => _monitoredAlerts;

  bool get isBackendMode => !_demoMode && _apiClient != null;
  bool get demoMode => _demoMode;
  bool get isRefreshing => _isRefreshing;
  String get modeLabel => isBackendMode ? 'LIVE' : 'DEMO';
  String get backendUrl => _backendUrl;
  ApiClient? get apiClient => _apiClient;

  BleDeviceService get bleService => _bleService;
  TransportOrchestrator? get transportOrchestrator => _transportOrchestrator;
  FirestoreSyncService? get firestoreSync => _firestoreSync;
  TransportType get activeTransport =>
      _transportOrchestrator?.activeTransport ?? TransportType.none;
  bool get isBleConnected => _bleService.isConnected;
  String get transportLabel =>
      _transportOrchestrator?.transportLabel ?? 'Bağlantı yok';
  bool get isFirestoreSyncAvailable => _firestoreSync?.isAvailable ?? false;

  String? get selectedMonitoredUserId =>
      _monitoredUsers.isNotEmpty ? _monitoredUsers.first.id : null;

  Future<void> initialize() async {
    _settings = await _settingsRepository.getSettings();
    _deviceState = await _deviceRepository.getState();
    _contacts = await _contactRepository.getContacts();
    _history = await _historyRepository.getHistory();
    _anomalies = await _anomalyRepository.getAnomalies();
    _notifications = await _notificationRepository.getNotifications();
    _activeAlert = await _alertRepository.getActiveAlert();

    final savedToken = await LocalStore.getString('auth_token');
    final savedRole = await LocalStore.getString('user_role');
    final savedUserId = await LocalStore.getString('session_user_id');

    if (savedToken != null && savedUserId != null) {
      _authToken = savedToken;
      _apiClient?.setToken(savedToken);
      try {
        if (isBackendMode) {
          final data = await _apiClient!.get('/users/me') as Map<String, dynamic>;
          _user = UserProfile.fromJson(data);
        } else {
          _user = await _userRepository.getProfile(savedUserId);
          if (savedRole != null) {
            final parsedRole = UserRole.values.firstWhere(
              (r) => r.name == savedRole,
              orElse: () => UserRole.self,
            );
            _user = _user!.copyWith(role: parsedRole);
          }
        }
        _authenticated = true;
        await _onAuthenticatedInit();
      } catch (e) {
        debugPrint('[AppController] Session restore failed: $e');
        await _clearSession();
      }
    }

    _initialized = true;
    notifyListeners();
  }

  Future<void> _onAuthenticatedInit() async {
    if (role == UserRole.self) {
      _startTransportLayer();
      _startLiveDataPolling();
      if (isBackendMode) {
        await _loadFromBackend();
      }
    } else {
      await loadMonitoredUsers();
      if (isBackendMode) {
        _startMonitoredLivePolling();
      }
    }
  }

  void _startTransportLayer() {
    if (_demoMode) return;

    _transportOrchestrator = TransportOrchestrator(
      bleService: _bleService,
      apiClient: _apiClient,
      userId: _user?.id ?? '',
      transportMode: _transportMode,
    );

    _transportPacketSub?.cancel();
    _transportPacketSub =
        _transportOrchestrator!.packetStream.listen(_onTransportPacket);

    _transportStatusSub?.cancel();
    _transportStatusSub =
        _transportOrchestrator!.statusStream.listen(_onTransportStatus);

    if (_firestoreSync?.isAvailable ?? false) {
      _firestoreSync!.stop();
      _firestoreSync = FirestoreSyncService(userId: _user?.id ?? '');
      _firestoreSync!.start();
    }

    _transportOrchestrator!.start();

    debugPrint('[AppController] Transport layer started for user ${_user?.id} (mode: $_transportMode)');
  }

  void _stopTransportLayer() {
    _transportPacketSub?.cancel();
    _transportPacketSub = null;
    _transportStatusSub?.cancel();
    _transportStatusSub = null;
    _transportOrchestrator?.stop();
    _firestoreSync?.stop();
  }

  void _onTransportPacket(BlePacket packet) {
    _firestoreSync?.addPacket(packet);

    if (isBackendMode && _apiClient != null) {
      _forwardPacketToBackend(packet);
    }
  }

  void _onTransportStatus(LiveStatus status) {
    _latestLiveStatus = status;

    _firestoreSync?.syncLiveStatus(status);

    notifyListeners();
  }

  Future<void> _forwardPacketToBackend(BlePacket packet) async {
    try {
      await _apiClient?.post('/ingest/device-packet', packet.toJson());
    } catch (e) {
      debugPrint('[AppController] Forward packet to backend failed: $e');
    }
  }

  Future<String?> switchToLive({String? url}) async {
    final backendUrl = url ?? _backendUrl;
    _backendUrl = backendUrl;
    final client = ApiClient(baseUrl: backendUrl);
    final reachable = await client.ping();
    if (!reachable) {
      return 'Canlı sunucuya ulaşılamadı.\nDemo moduna devam ediliyor.';
    }
    final savedToken = await LocalStore.getString('auth_token');
    if (savedToken != null) {
      client.setToken(savedToken);
    }
    _apiClient = client;
    _demoMode = false;
    _isRefreshing = true;
    notifyListeners();
    try {
      if (_authenticated) {
        await _loadFromBackend();
        if (role == UserRole.self) {
          _startTransportLayer();
          _startLiveDataPolling();
        } else {
          await loadMonitoredUsers();
          _startMonitoredLivePolling();
        }
      }
    } catch (_) {
    } finally {
      _isRefreshing = false;
      notifyListeners();
    }
    return null;
  }

  void switchToDemo() {
    _demoMode = true;
    _apiClient?.clearToken();
    _apiClient = null;
    _stopTransportLayer();
    _stopMonitoredLivePolling();
    if (role == UserRole.self) {
      _startLiveDataPolling();
    }
    notifyListeners();
  }

  Future<void> _loadFromBackend() async {
    if (!isBackendMode || _user == null) return;

    try {
      final List<dynamic> anomalyData = await _apiClient!.get('/anomalies') as List<dynamic>;
      _anomalies = anomalyData
          .map((e) => AnomalyEvent.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('[AppController] anomalies load failed: $e');
    }

    try {
      final List<dynamic> historyData = await _apiClient!.get('/history') as List<dynamic>;
      _history = historyData
          .map((e) => _historyFromApiJson(e as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('[AppController] history load failed: $e');
    }

    try {
      final List<dynamic> notifData = await _apiClient!.get('/notifications') as List<dynamic>;
      _notifications = notifData
          .map((e) => _notifFromApiJson(e as Map<String, dynamic>))
          .toList();
    } catch (e) {
      debugPrint('[AppController] notifications load failed: $e');
    }

    try {
      final alertData = await _apiClient!.get('/alerts/active');
      if (alertData != null && alertData is Map<String, dynamic>) {
        _activeAlert = _alertFromApiJson(alertData);
      }
    } catch (e) {
      debugPrint('[AppController] active alert load failed: $e');
    }

    try {
      final List<dynamic> relData =
          await _apiClient!.get('/link-codes/relations') as List<dynamic>;
      _relations =
          relData.map((e) => UserRelation.fromJson(e as Map<String, dynamic>)).toList();
    } catch (e) {
      debugPrint('[AppController] relations load failed: $e');
    }

    notifyListeners();
  }

  int _intervalForBatteryMode(BatteryMode mode) {
    if (_demoMode) {
      switch (mode) {
        case BatteryMode.performance:
          return 2;
        case BatteryMode.balanced:
          return 4;
        case BatteryMode.saver:
          return 8;
      }
    } else {
      switch (mode) {
        case BatteryMode.performance:
          return 10;
        case BatteryMode.balanced:
          return 30;
        case BatteryMode.saver:
          return 120;
      }
    }
  }

  void _startLiveDataPolling() {
    _liveDataService?.dispose();
    final interval = _intervalForBatteryMode(_settings.batteryMode);
    _liveDataService = LiveDataService(demoMode: _demoMode);
    _liveDataService!.start(
      userId: _user?.id ?? 'demo',
      intervalSeconds: interval,
      fetchFn: isBackendMode && _user != null
          ? () async {
              try {
                final data = await _apiClient!.get('/live/${_user!.id}');
                if (data is Map<String, dynamic>) return LiveStatus.fromJson(data);
              } catch (e) {
                debugPrint('[AppController] Live status fetch failed: $e');
              }
              return null;
            }
          : null,
    );
    _liveDataService!.stream.listen((status) {
      _latestLiveStatus = status;
      notifyListeners();
    });
  }

  void stopLiveDataPolling() {
    _liveDataService?.stop();
  }

  int _intervalForMonitoredLive(BatteryMode mode) {
    switch (mode) {
      case BatteryMode.performance:
        return isBackendMode ? 4 : 8;
      case BatteryMode.balanced:
        return isBackendMode ? 8 : 12;
      case BatteryMode.saver:
        return isBackendMode ? 16 : 20;
    }
  }

  void _startMonitoredLivePolling() {
    _stopMonitoredLivePolling();
    if (!isBackendMode || _user == null) return;

    final intervalSec = _intervalForMonitoredLive(_settings.batteryMode);
    _refreshMonitoredLiveStatuses();
    _monitoredLiveTimer = Timer.periodic(Duration(seconds: intervalSec), (_) {
      _refreshMonitoredLiveStatuses();
    });
  }

  void _stopMonitoredLivePolling() {
    _monitoredLiveTimer?.cancel();
    _monitoredLiveTimer = null;
  }

  Future<void> _refreshMonitoredLiveStatuses() async {
    if (!isBackendMode || _monitoredLiveRefreshing) return;
    _monitoredLiveRefreshing = true;
    try {
      if (_monitoredUsers.isEmpty) return;
      var changed = false;
      for (final user in _monitoredUsers) {
        try {
          final live = await getLiveStatusForUser(user.id, notify: false);
          if (live != null) {
            final prev = _monitoredLiveStatuses[user.id];
            if (prev == null || prev.timestamp != live.timestamp || prev.scenario != live.scenario) {
              changed = true;
            }
          }
        } catch (_) {
        }
      }
      if (changed) notifyListeners();
    } finally {
      _monitoredLiveRefreshing = false;
    }
  }

  Future<bool> login(String email, String password) async {
    if (email.trim().isEmpty || password.trim().isEmpty) return false;

    if (isBackendMode) {
      return _loginViaApi(email.trim(), password);
    }
    return _loginMock(email.trim(), password);
  }

  Future<bool> _loginViaApi(String email, String password) async {
    try {
      final data = await _apiClient!.post(
        '/auth/login',
        {'email': email, 'password': password},
        auth: false,
      );
      _authToken = data['access_token'] as String;
      final userId = data['user_id'] as String;
      final roleStr = (data['role'] as String).toLowerCase();
      _apiClient!.setToken(_authToken!);

      await LocalStore.setString('auth_token', _authToken!);
      await LocalStore.setString('session_user_id', userId);
      await LocalStore.setString('user_role', roleStr);

      final role = UserRole.values.firstWhere(
        (r) => r.name == roleStr,
        orElse: () => UserRole.self,
      );
      final userData = await _apiClient!.get('/users/me') as Map<String, dynamic>;
      _user = UserProfile.fromJson(userData);

      _authenticated = true;
      await _onAuthenticatedInit();
      notifyListeners();
      return true;
    } on ApiException {
      return false;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _loginMock(String email, String password) async {
    final demoPairs = {
      'self@demo.com': UserRole.self,
      'relative@demo.com': UserRole.relative,
      'doctor@demo.com': UserRole.doctor,
    };

    UserRole? mappedRole;
    if (password == 'demo1234' && demoPairs.containsKey(email.toLowerCase())) {
      mappedRole = demoPairs[email.toLowerCase()]!;
    } else if (password.length >= 4) {
      mappedRole = UserRole.self;
    }

    if (mappedRole == null) return false;

    const userId = 'u1';
    _user = (await _userRepository.getProfile(userId)).copyWith(role: mappedRole);
    await _sessionRepository.saveSession(userId);
    await LocalStore.setString('user_role', mappedRole.name);
    _authenticated = true;
    await _onAuthenticatedInit();
    notifyListeners();
    return true;
  }

  Future<bool> register({
    required String email,
    required String password,
    required String fullName,
    required UserRole role,
    String? phone,
    String? birthDate,
  }) async {
    if (!isBackendMode) {
      return _loginMock(email, password.isEmpty ? 'demo1234' : password);
    }

    try {
      final data = await _apiClient!.post('/auth/register', {
        'email': email.trim(),
        'password': password,
        'role': role.name.toUpperCase(),
        'full_name': fullName.trim(),
        if (phone != null) 'phone': phone,
        if (birthDate != null) 'birth_date': birthDate,
      }, auth: false);

      _authToken = data['access_token'] as String;
      _apiClient!.setToken(_authToken!);
      await LocalStore.setString('auth_token', _authToken!);
      await LocalStore.setString('session_user_id', data['user_id'] as String);
      await LocalStore.setString('user_role', role.name);

      final userData = await _apiClient!.get('/users/me') as Map<String, dynamic>;
      _user = UserProfile.fromJson(userData);

      _authenticated = true;
      await _onAuthenticatedInit();
      notifyListeners();
      return true;
    } on ApiException {
      return false;
    } catch (e) {
      debugPrint('[AppController] Registration failed: $e');
      return false;
    }
  }

  Future<void> logout() async {
    _alertTimer?.cancel();
    _liveDataService?.dispose();
    _liveDataService = null;
    _stopMonitoredLivePolling();
    _stopTransportLayer();
    _activeAlert = null;
    _authenticated = false;
    _user = null;
    _authToken = null;
    _apiClient?.clearToken();
    _relations = const [];
    _linkCodes = const [];
    _monitoredUsers = const [];
    _monitoredLiveStatuses.clear();
    _monitoredAlerts.clear();
    _clinicalNotes.clear();
    await _clearSession();
    notifyListeners();
  }

  Future<void> _clearSession() async {
    await _sessionRepository.clearSession();
    await LocalStore.remove('auth_token');
    await LocalStore.remove('user_role');
    await LocalStore.remove('session_user_id');
  }

  Future<void> updateProfile(UserProfile profile) async {
    if (isBackendMode) {
      try {
        final data = await _apiClient!.put('/users/me', {
          'full_name': profile.fullName,
          'phone': profile.phone,
          'birth_date': profile.birthDate,
        });
        _user = UserProfile.fromJson(data).copyWith(role: role);
      } catch (_) {
        _user = profile;
      }
    } else {
      _user = await _userRepository.updateProfile(profile);
    }
    notifyListeners();
  }

  Future<void> saveSettings(AppSettings s) async {
    final previousBatteryMode = _settings.batteryMode;
    _settings = await _settingsRepository.saveSettings(s);
    _deviceState = _deviceState.copyWith(mode: s.batteryMode, lastSync: DateTime.now());
    await _deviceRepository.saveState(_deviceState);

    if (role == UserRole.self && s.batteryMode != previousBatteryMode) {
      _startLiveDataPolling();
    }
    if (role != UserRole.self && s.batteryMode != previousBatteryMode && isBackendMode) {
      _startMonitoredLivePolling();
    }

    if (isBackendMode) {
      try {
        await _apiClient!.put('/settings', {
          'notifications_enabled': s.notificationsEnabled,
          'battery_mode': s.batteryMode.name,
          'background_monitoring': s.backgroundMonitoring,
          'update_interval_seconds': s.uploadIntervalMinutes * 60,
        });
      } catch (_) {}
    }
    notifyListeners();
  }

  Future<void> loadSettings() async {
    if (isBackendMode) {
      try {
        final data = await _apiClient!.get('/settings') as Map<String, dynamic>;
        final batteryModeStr = data['battery_mode'] as String? ?? 'balanced';
        _settings = AppSettings(
          hrHighThreshold: _settings.hrHighThreshold,
          hrLowThreshold: _settings.hrLowThreshold,
          notificationsEnabled: data['notifications_enabled'] as bool? ?? true,
          batteryMode: BatteryMode.values.firstWhere(
            (m) => m.name == batteryModeStr,
            orElse: () => BatteryMode.balanced,
          ),
          dimBrightness: _settings.dimBrightness,
          backgroundMonitoring: data['background_monitoring'] as bool? ?? true,
          uploadIntervalMinutes: _settings.uploadIntervalMinutes,
        );
        notifyListeners();
      } catch (_) {}
    }
  }

  Future<void> markNotificationsRead() async {
    if (isBackendMode) {
      try {
        await _apiClient!.put('/notifications/read-all', {});
      } catch (_) {}
    }
    await _notificationRepository.markAllRead();
    _notifications = await _notificationRepository.getNotifications();
    notifyListeners();
  }

  Future<void> refreshNotifications() async {
    if (isBackendMode) {
      try {
        final List<dynamic> data = await _apiClient!.get('/notifications') as List<dynamic>;
        _notifications = data
            .map((e) => _notifFromApiJson(e as Map<String, dynamic>))
            .toList();
        notifyListeners();
        return;
      } catch (_) {}
    }
    _notifications = await _notificationRepository.getNotifications();
    notifyListeners();
  }

  Future<void> simulateAnomaly({
    required String metric,
    required double value,
    required String unit,
    required double score,
    String? summary,
  }) async {
    final sev = _stateMachine.mapScoreToSeverity(score);
    final anomaly = AnomalyEvent(
      id: 'an_${DateTime.now().millisecondsSinceEpoch}',
      metric: metric,
      value: value,
      unit: unit,
      severity: sev,
      detectedAt: DateTime.now(),
      summary: summary ?? 'Anomaly detected for $metric',
    );

    await _anomalyRepository.addAnomaly(anomaly);
    _anomalies = await _anomalyRepository.getAnomalies();

    await _historyRepository.addHistory(
      HistoryItem(
        id: 'h_${DateTime.now().microsecondsSinceEpoch}',
        type: HistoryItemType.anomaly,
        title: '${anomaly.metric} anomaly',
        subtitle: '${anomaly.value.toStringAsFixed(1)} ${anomaly.unit}',
        timestamp: anomaly.detectedAt,
        severity: anomaly.severity,
      ),
    );
    _history = await _historyRepository.getHistory();

    if (sev == AlertSeverity.warning || sev == AlertSeverity.critical) {
      await raiseAlertFromAnomaly(anomaly);
    }

    notifyListeners();
  }

  Future<void> raiseAlertFromAnomaly(AnomalyEvent anomaly) async {
    final recommendations = _recommendationService.forSeverity(anomaly.severity);
    final alert = AlertEvent(
      id: 'al_${DateTime.now().millisecondsSinceEpoch}',
      title: '${anomaly.metric} alert',
      description: anomaly.summary,
      severity: anomaly.severity,
      status: AlertLifecycleStatus.raised,
      createdAt: DateTime.now(),
      countdownTotalSec: anomaly.severity == AlertSeverity.critical ? 30 : 20,
      countdownRemainingSec: anomaly.severity == AlertSeverity.critical ? 30 : 20,
      recommendations: recommendations,
      relatedAnomalyId: anomaly.id,
    );

    _activeAlert = _stateMachine.beginCountdown(alert);
    await _alertRepository.upsertAlert(_activeAlert!);
    await _historyRepository.addHistory(
      HistoryItem(
        id: 'h_${DateTime.now().microsecondsSinceEpoch}',
        type: HistoryItemType.alert,
        title: _activeAlert!.title,
        subtitle: _activeAlert!.description,
        timestamp: _activeAlert!.createdAt,
        severity: _activeAlert!.severity,
      ),
    );

    await _notificationRepository.addNotification(
      NotificationItem(
        id: 'n_${DateTime.now().millisecondsSinceEpoch}',
        title: 'Alarm Başlatıldı',
        body: _activeAlert!.title,
        channel: NotificationChannel.local,
        createdAt: DateTime.now(),
        read: false,
      ),
    );

    _history = await _historyRepository.getHistory();
    _notifications = await _notificationRepository.getNotifications();

    _startAlertCountdown();
    notifyListeners();
  }

  Future<void> confirmImOkay() async {
    if (_activeAlert == null) return;
    _alertTimer?.cancel();

    if (isBackendMode) {
      try {
        await _apiClient!.put('/alerts/${_activeAlert!.id}/respond', {'action': 'OKAY'});
      } catch (_) {}
    }

    _activeAlert = _stateMachine.onImOkay(_activeAlert!);
    _activeAlert = _stateMachine.toPostEvent(_activeAlert!);
    await _alertRepository.upsertAlert(_activeAlert!);

    await _notificationRepository.addNotification(
      NotificationItem(
        id: 'n_${DateTime.now().millisecondsSinceEpoch}',
        title: 'Kullanıcı Durumu Onayladı',
        body: 'Olay sonrası izleme başlatıldı.',
        channel: NotificationChannel.inApp,
        createdAt: DateTime.now(),
        read: false,
      ),
    );

    _notifications = await _notificationRepository.getNotifications();
    notifyListeners();
  }

  Future<void> requestEmergency() async {
    if (_activeAlert == null) return;
    _alertTimer?.cancel();

    if (isBackendMode) {
      try {
        await _apiClient!.put('/alerts/${_activeAlert!.id}/respond', {'action': 'EMERGENCY'});
      } catch (_) {}
    }

    _activeAlert = _stateMachine.onEmergency(_activeAlert!);
    _activeAlert = _stateMachine.toPostEvent(_activeAlert!);
    await _alertRepository.upsertAlert(_activeAlert!);

    await _notificationRepository.addNotification(
      NotificationItem(
        id: 'n_${DateTime.now().millisecondsSinceEpoch}',
        title: 'Acil Yardım İstendi',
        body: 'Acil kişiler bilgilendirildi.',
        channel: NotificationChannel.local,
        createdAt: DateTime.now(),
        read: false,
      ),
    );

    _notifications = await _notificationRepository.getNotifications();
    notifyListeners();
  }

  Future<void> closePostEvent() async {
    if (_activeAlert == null) return;
    _alertTimer?.cancel();
    _activeAlert = _stateMachine.close(_activeAlert!);
    await _alertRepository.upsertAlert(_activeAlert!);
    _activeAlert = null;
    notifyListeners();
  }

  void _startAlertCountdown() {
    _alertTimer?.cancel();
    _alertTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      if (_activeAlert == null) {
        timer.cancel();
        return;
      }

      _activeAlert = _stateMachine.tick(_activeAlert!);
      await _alertRepository.upsertAlert(_activeAlert!);

      if (_activeAlert!.status == AlertLifecycleStatus.timedOut) {
        _activeAlert = _stateMachine.toPostEvent(_activeAlert!);
        await _alertRepository.upsertAlert(_activeAlert!);
        await _notificationRepository.addNotification(
          NotificationItem(
            id: 'n_${DateTime.now().millisecondsSinceEpoch}',
            title: 'Kullanıcı Yanıt Vermedi',
            body: 'Alarm otomatik olarak olay sonrası izlemeye geçti.',
            channel: NotificationChannel.local,
            createdAt: DateTime.now(),
            read: false,
          ),
        );
        _notifications = await _notificationRepository.getNotifications();
        timer.cancel();
      }

      notifyListeners();
    });
  }

  Future<LinkCode?> generateLinkCode({required String relationType}) async {
    if (role != UserRole.self) return null;

    if (isBackendMode) {
      try {
        final data = await _apiClient!.post('/link-codes/generate', {
          'relation_type': relationType,
        }) as Map<String, dynamic>;
        final code = LinkCode.fromJson(data);
        _linkCodes = [code, ..._linkCodes];
        notifyListeners();
        return code;
      } catch (_) {
        return null;
      }
    }
    final mock = LinkCode(
      id: 'lc_${DateTime.now().millisecondsSinceEpoch}',
      code: '${100000 + DateTime.now().millisecondsSinceEpoch % 900000}',
      codeType: relationType.toUpperCase(),
      isActive: true,
      usesRemaining: 1,
      expiresAt: DateTime.now().add(const Duration(hours: 48)),
      createdAt: DateTime.now(),
    );
    _linkCodes = [mock, ..._linkCodes];
    notifyListeners();
    return mock;
  }

  Future<void> loadLinkCodes() async {
    if (isBackendMode) {
      try {
        final List<dynamic> data = await _apiClient!.get('/link-codes/mine') as List<dynamic>;
        _linkCodes = data.map((e) => LinkCode.fromJson(e as Map<String, dynamic>)).toList();
        notifyListeners();
      } catch (_) {}
    }
  }

  Future<String?> redeemCode(String code) async {
    if (role == UserRole.self) {
      return 'Sadece Yakın veya Doktor kod girebilir.';
    }

    if (isBackendMode) {
      try {
        await _apiClient!.post('/link-codes/redeem', {'code': code});
        await loadRelations();
        await loadMonitoredUsers();
        _refreshMonitoredLiveStatuses(); // fire-and-forget
        return null; // success
      } on ApiException catch (e) {
        return e.message;
      } catch (_) {
        return 'Bağlantı hatası';
      }
    }
    await loadRelations();
    await loadMonitoredUsers();
    return null;
  }

  Future<void> loadRelations() async {
    if (isBackendMode) {
      try {
        final List<dynamic> data = await _apiClient!.get('/link-codes/relations') as List<dynamic>;
        _relations = data.map((e) => UserRelation.fromJson(e as Map<String, dynamic>)).toList();
        notifyListeners();
      } catch (_) {}
    }
  }

  Future<void> removeRelation(String relationId) async {
    if (isBackendMode) {
      try {
        await _apiClient!.delete('/link-codes/relations/$relationId');
        _relations = _relations.where((r) => r.id != relationId).toList();
        _monitoredUsers = _monitoredUsers.where((u) {
          return _relations.any((r) => r.selfUserId == u.id);
        }).toList();
        notifyListeners();
      } catch (_) {}
    }
  }

  bool _monitoredUsersLoading = false;

  Future<void> loadMonitoredUsers() async {
    if (_monitoredUsersLoading) return;
    _monitoredUsersLoading = true;
    try {
      if (isBackendMode) {
        try {
          final List<dynamic> relData = await _apiClient!.get('/link-codes/relations') as List<dynamic>;
          _relations = relData.map((e) => UserRelation.fromJson(e as Map<String, dynamic>)).toList();

          final users = <UserProfile>[];
          for (final rel in _relations) {
            try {
              final userData = await _apiClient!.get('/users/${rel.selfUserId}') as Map<String, dynamic>;
              users.add(UserProfile.fromJson(userData));
            } catch (_) {}
          }
          _monitoredUsers = users;
        } catch (e) {
          debugPrint('[AppController] loadMonitoredUsers failed: $e');
        }
      } else {
        _monitoredUsers = const [
        UserProfile(
          id: 'demo_self_1',
          fullName: 'Ali Yilmaz',
          email: 'ali@demo.com',
          phone: '+90 555 100 0001',
          birthDate: '1965-03-15',
          deviceId: 'WH-DEMO-01',
          role: UserRole.self,
        ),
        UserProfile(
          id: 'demo_self_2',
          fullName: 'Fatma Demir',
          email: 'fatma@demo.com',
          phone: '+90 555 100 0002',
          birthDate: '1970-08-21',
          deviceId: 'WH-DEMO-02',
          role: UserRole.self,
        ),
        UserProfile(
          id: 'demo_self_3',
          fullName: 'Mehmet Kaya',
          email: 'mehmet@demo.com',
          phone: '+90 555 100 0003',
          birthDate: '1958-01-03',
          deviceId: 'WH-DEMO-03',
          role: UserRole.self,
        ),
      ];
      }
      notifyListeners();
    } finally {
      _monitoredUsersLoading = false;
    }
  }

  Future<LiveStatus?> getLiveStatusForUser(String userId, {bool notify = true}) async {
    if (isBackendMode) {
      try {
        final data = await _apiClient!.get('/live/$userId') as Map<String, dynamic>;
        final live = LiveStatus.fromJson(data);
        _monitoredLiveStatuses[userId] = live;
        if (notify) notifyListeners();
        return live;
      } catch (_) {
        return _monitoredLiveStatuses[userId];
      }
    }
    final now = DateTime.now();
    final seed = userId.codeUnits.fold<int>(0, (sum, ch) => sum + ch);
    final profile = seed % 3;
    final wave = math.sin((now.millisecondsSinceEpoch / 1000.0) + seed / 10.0);

    double clamp(double v, double min, double max) => v < min ? min : (v > max ? max : v);

    double heartRate;
    double spo2;
    double motion;
    double risk;
    String scenario;

    if (profile == 0) {
      heartRate = 72 + (wave * 6);
      spo2 = 97.2 + (wave * 0.6);
      motion = clamp(0.18 + (wave.abs() * 0.12), 0.05, 0.45);
      risk = clamp(0.12 + (wave.abs() * 0.08), 0.05, 0.28);
      scenario = 'normal';
    } else if (profile == 1) {
      heartRate = 98 + (wave * 12);
      spo2 = 94.0 + (wave * 1.1);
      motion = clamp(0.38 + (wave.abs() * 0.22), 0.12, 0.88);
      risk = clamp(0.52 + (wave.abs() * 0.18), 0.35, 0.78);
      scenario = risk > 0.62 ? 'warning' : 'elevated_hr';
    } else {
      heartRate = 116 + (wave * 10);
      spo2 = 90.5 + (wave * 1.2);
      motion = clamp(0.62 + (wave.abs() * 0.2), 0.22, 0.95);
      risk = clamp(0.74 + (wave.abs() * 0.2), 0.55, 0.96);
      scenario = risk > 0.82 ? 'critical' : 'low_spo2';
    }

    final demoLive = LiveStatus(
      id: 'demo_live',
      userId: userId,
      heartRate: clamp(heartRate, 45, 180),
      spo2: clamp(spo2, 82, 100),
      motionScore: motion,
      riskScore: risk,
      scenario: scenario,
      timestamp: now,
    );
    _monitoredLiveStatuses[userId] = demoLive;
    if (notify) notifyListeners();
    return demoLive;
  }

  Future<List<AlertEvent>> getAlertsForUser(String userId) async {
    if (isBackendMode) {
      try {
        final List<dynamic> data =
            await _apiClient!.get('/alerts/$userId/for-linked') as List<dynamic>;
        return data.map((e) => _alertFromApiJson(e as Map<String, dynamic>)).toList();
      } catch (_) {
        return const [];
      }
    }
    final now = DateTime.now();
    return [
      AlertEvent(
        id: 'demo_alert_1',
        userId: userId,
        title: 'Yüksek Nabız Uyarısı',
        description: 'Nabız 118 bpm ile uyarı eşiğini aştı.',
        severity: AlertSeverity.warning,
        status: AlertLifecycleStatus.acknowledged,
        createdAt: now.subtract(const Duration(hours: 2)),
        countdownTotalSec: 20,
        countdownRemainingSec: 0,
        recommendations: ['Oturun ve sakin olun.', 'Vital değerleri izleyin.'],
        relatedAnomalyId: null,
      ),
      AlertEvent(
        id: 'demo_alert_2',
        userId: userId,
        title: 'Kritik SpO2 Alarmı',
        description: 'Oksijen doygunluğu %88\'e düştü.',
        severity: AlertSeverity.critical,
        status: AlertLifecycleStatus.closed,
        createdAt: now.subtract(const Duration(days: 3)),
        countdownTotalSec: 30,
        countdownRemainingSec: 0,
        recommendations: ['Acil risk tespit edildi.', 'Bulunduğunuz yerde kalın.'],
        relatedAnomalyId: null,
      ),
    ];
  }

  Future<List<HistoryItem>> getHistoryForUser(String userId) async {
    if (isBackendMode) {
      try {
        final List<dynamic> data = await _apiClient!.get('/history/$userId') as List<dynamic>;
        return data.map((e) => _historyFromApiJson(e as Map<String, dynamic>)).toList();
      } catch (_) {
        return const [];
      }
    }
    final now = DateTime.now();
    return [
      HistoryItem(
        id: 'demo_h1',
        type: HistoryItemType.alert,
        title: 'Kritik SpO2 Alarmı',
        subtitle: 'Oksijen doygunluğu %88\'e düştü. Acil kişiler bilgilendirildi.',
        timestamp: now.subtract(const Duration(days: 3)),
        severity: AlertSeverity.critical,
      ),
      HistoryItem(
        id: 'demo_h2',
        type: HistoryItemType.anomaly,
        title: 'Nabız Anomalisi',
        subtitle: 'Sabah izlemesinde nabız 124 bpm\'e ulaştı.',
        timestamp: now.subtract(const Duration(days: 2)),
        severity: AlertSeverity.warning,
      ),
      HistoryItem(
        id: 'demo_h3',
        type: HistoryItemType.status,
        title: 'İzleme Sürdürüldü',
        subtitle: 'Dinlendikten sonra vital değerler normale döndü.',
        timestamp: now.subtract(const Duration(days: 2, hours: 1)),
        severity: AlertSeverity.normal,
      ),
    ];
  }

  Future<List<ClinicalNote>> getClinicalNotes(String patientId) async {
    if (_clinicalNotes.containsKey(patientId)) return _clinicalNotes[patientId]!;

    if (isBackendMode) {
      try {
        final List<dynamic> data =
            await _apiClient!.get('/clinical-notes/$patientId') as List<dynamic>;
        final notes = data.map((e) => ClinicalNote.fromJson(e as Map<String, dynamic>)).toList();
        _clinicalNotes[patientId] = notes;
        return notes;
      } catch (_) {}
    }
    _clinicalNotes[patientId] ??= [];
    return _clinicalNotes[patientId]!;
  }

  Future<ClinicalNote?> addClinicalNote(
    String patientId,
    String note, {
    String? recommendation,
  }) async {
    if (isBackendMode) {
      try {
        final data = await _apiClient!.post('/clinical-notes', {
          'patient_id': patientId,
          'note': note,
          if (recommendation != null) 'recommendation': recommendation,
        }) as Map<String, dynamic>;
        final created = ClinicalNote.fromJson(data);
        _clinicalNotes[patientId] = [created, ...(_clinicalNotes[patientId] ?? [])];
        notifyListeners();
        return created;
      } catch (_) {}
    }

    final mock = ClinicalNote(
      id: 'note_${DateTime.now().millisecondsSinceEpoch}',
      doctorId: _user?.id ?? 'doc',
      patientId: patientId,
      note: note,
      recommendation: recommendation,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
    _clinicalNotes[patientId] = [mock, ...(_clinicalNotes[patientId] ?? [])];
    notifyListeners();
    return mock;
  }

  static HistoryItem _historyFromApiJson(Map<String, dynamic> json) {
    return HistoryItem.fromJson(json);
  }

  static NotificationItem _notifFromApiJson(Map<String, dynamic> json) {
    return NotificationItem.fromJson(json);
  }

  static AlertEvent _alertFromApiJson(Map<String, dynamic> json) {
    return AlertEvent.fromJson(json);
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _alertTimer?.cancel();
    _liveDataService?.dispose();
    _stopMonitoredLivePolling();
    _stopTransportLayer();
    _bleService.dispose();
    super.dispose();
  }
}

