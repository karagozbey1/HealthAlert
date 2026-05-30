import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import 'ble_device_service.dart';
import 'api_client.dart';
import 'local_risk_calculator.dart';
import '../models/live_status.dart';

/// Mobil uygulamanın aktif telemetri taşıma kanalını tanımlar.
enum TransportType { none, ble, wifi }

/// BLE ve Wi-Fi kaynaklarını seçilen moda göre birlikte yönetir.
class TransportOrchestrator extends ChangeNotifier {
  TransportOrchestrator({
    required this.bleService,
    this.apiClient,
    this.userId = '',
    this.transportMode = 'auto',
  });

  final BleDeviceService bleService;
  final ApiClient? apiClient;
  final String userId;

  final String transportMode;

  TransportType _activeTransport = TransportType.none;
  bool _wifiAvailable = false;
  bool _autoFallbackEnabled = true;

  StreamSubscription<BlePacket>? _bleSub;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  Timer? _fallbackTimer;
  Timer? _bleRetryTimer;

  final _packetController = StreamController<BlePacket>.broadcast();
  final _statusController = StreamController<LiveStatus>.broadcast();

  int _blePackets = 0;
  int _wifiPolls = 0;
  DateTime? _lastDataTime;

  // BPM smoothing state
  double? _stableBpm;
  double? _pendingBpm;
  int _pendingBpmConfirm = 0;

  // SpO2 last-valid retention state
  double? _stableSpo2;
  DateTime? _lastSpo2ValidAt;

  // Motion score EMA (smooths per-packet jumps)
  double _motionScoreEma = 0.0;

  TransportType get activeTransport => _activeTransport;
  bool get wifiAvailable => _wifiAvailable;
  bool get autoFallbackEnabled => _autoFallbackEnabled;
  bool get isReceivingData =>
      _lastDataTime != null &&
      DateTime.now().difference(_lastDataTime!).inSeconds < 10;
  int get blePackets => _blePackets;
  int get wifiPolls => _wifiPolls;
  DateTime? get lastDataTime => _lastDataTime;

  Stream<BlePacket> get packetStream => _packetController.stream;
  Stream<LiveStatus> get statusStream => _statusController.stream;

  String get transportLabel {
    switch (_activeTransport) {
      case TransportType.ble:
        return 'BLE';
      case TransportType.wifi:
        return 'Wi-Fi';
      case TransportType.none:
        return 'Bağlantı yok';
    }
  }

  /// Servisin periyodik veri akışını başlatır.
  void start() {
    debugPrint(
        '[Transport] Starting transport orchestrator (mode: $transportMode)...');

    _connectivitySub?.cancel();
    _connectivitySub = Connectivity().onConnectivityChanged.listen((results) {
      _wifiAvailable = results.any((r) =>
          r == ConnectivityResult.wifi || r == ConnectivityResult.ethernet);
      notifyListeners();
    });

    Connectivity().checkConnectivity().then((results) {
      _wifiAvailable = results.any((r) =>
          r == ConnectivityResult.wifi || r == ConnectivityResult.ethernet);
    });

    switch (transportMode) {
      case 'off':
        _autoFallbackEnabled = false;
        _setTransport(TransportType.none);
        break;
      case 'wifi_only':
        _autoFallbackEnabled = false;
        _startWifiFallback();
        break;
      case 'ble_only':
        _autoFallbackEnabled = false;
        bleService.addListener(_onBleStateChanged);
        _bleSub = bleService.packetStream.listen(_onBlePacket);
        _startBle();
        break;
      case 'auto':
      default:
        _autoFallbackEnabled = true;
        bleService.addListener(_onBleStateChanged);
        _bleSub = bleService.packetStream.listen(_onBlePacket);
        _startBle();
        break;
    }
  }

  /// Servisin çalışan periyodik veri akışını durdurur.
  void stop() {
    _bleSub?.cancel();
    _bleSub = null;
    _connectivitySub?.cancel();
    _connectivitySub = null;
    _fallbackTimer?.cancel();
    _fallbackTimer = null;
    _bleRetryTimer?.cancel();
    _bleRetryTimer = null;
    bleService.removeListener(_onBleStateChanged);
    bleService.disconnect();
    _setTransport(TransportType.none);
    // Reset smoothing state on disconnect
    _stableBpm = null;
    _pendingBpm = null;
    _pendingBpmConfirm = 0;
    _stableSpo2 = null;
    _lastSpo2ValidAt = null;
    _motionScoreEma = 0.0;
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  void forceTransport(TransportType type) {
    _autoFallbackEnabled = false;
    switch (type) {
      case TransportType.ble:
        _startBle();
        break;
      case TransportType.wifi:
        _startWifiFallback();
        break;
      case TransportType.none:
        stop();
        break;
    }
    notifyListeners();
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  void enableAutoFallback() {
    _autoFallbackEnabled = true;
    notifyListeners();
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    stop();
    _packetController.close();
    _statusController.close();
    super.dispose();
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  void _setTransport(TransportType type) {
    if (_activeTransport != type) {
      _activeTransport = type;
      debugPrint('[Transport] Active transport: ${type.name}');
      notifyListeners();
    }
  }

  /// İlgili timer, listener veya bağlantı akışını başlatır.
  void _startBle() {
    debugPrint('[Transport] Starting BLE scan...');
    bleService.startScan();

    _fallbackTimer?.cancel();
    if (_autoFallbackEnabled && apiClient != null && userId.isNotEmpty) {
      _fallbackTimer = Timer(const Duration(seconds: 16), () {
        if (!bleService.isConnected) {
          debugPrint('[Transport] BLE timeout → switching to Wi-Fi fallback');
          _startWifiFallback();
        }
      });
    }
  }

  /// İlgili timer, listener veya bağlantı akışını başlatır.
  void _startWifiFallback() {
    if (apiClient == null || userId.isEmpty) {
      debugPrint(
          '[Transport] Wi-Fi fallback unavailable without backend/user; keeping BLE local mode.');
      _setTransport(TransportType.none);
      if (_autoFallbackEnabled) {
        _startBle();
      }
      return;
    }

    debugPrint('[Transport] Activating Wi-Fi fallback (HTTP polling)...');
    _setTransport(TransportType.wifi);

    _fallbackTimer?.cancel();
    _fallbackTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _pollViaWifi();
    });
    _pollViaWifi();

    if (_autoFallbackEnabled) {
      _bleRetryTimer?.cancel();
      _bleRetryTimer = Timer.periodic(const Duration(seconds: 30), (_) {
        if (_activeTransport == TransportType.wifi && !bleService.isConnected) {
          debugPrint('[Transport] Retrying BLE scan from Wi-Fi fallback...');
          bleService.startScan();
        }
      });
    }
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  Future<void> _pollViaWifi() async {
    if (apiClient == null || userId.isEmpty) return;

    try {
      final data = await apiClient!.get('/live/$userId');
      if (data is Map<String, dynamic>) {
        final status = LiveStatus.fromJson(data);
        _wifiPolls++;
        _lastDataTime = DateTime.now();
        if (!_statusController.isClosed) {
          _statusController.add(status);
        }
      }
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        debugPrint('[Transport] Wi-Fi poll got 401 — stopping transport.');
        stop();
        return;
      }
      debugPrint('[Transport] Wi-Fi poll failed: $e');
    } catch (e) {
      debugPrint('[Transport] Wi-Fi poll failed: $e');
    }
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  void _onBleStateChanged() {
    final bleState = bleService.state;

    if (bleState == BleConnectionState.connected) {
      _fallbackTimer?.cancel();
      _bleRetryTimer?.cancel();
      _bleRetryTimer = null;
      _setTransport(TransportType.ble);
    } else if (bleState == BleConnectionState.disconnected &&
        _activeTransport == TransportType.ble) {
      debugPrint('[Transport] BLE disconnected → falling back to Wi-Fi');
      if (_autoFallbackEnabled) {
        _startWifiFallback();
      } else {
        _setTransport(TransportType.none);
      }
    }
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  void _onBlePacket(BlePacket packet) {
    _blePackets++;
    _lastDataTime = DateTime.now();

    if (!_packetController.isClosed) {
      _packetController.add(packet);
    }

    final raw = packet.toLiveStatus(userId);
    final enriched = _enrichStatus(raw, packet);
    if (!_statusController.isClosed) {
      _statusController.add(enriched);
    }
  }

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  LiveStatus _enrichStatus(LiveStatus raw, BlePacket packet) {
    // --- Motion score EMA (alpha=0.20, smooths 1-packet spikes) ---
    const double motionAlpha = 0.20;
    _motionScoreEma =
        _motionScoreEma * (1 - motionAlpha) + raw.motionScore * motionAlpha;

    // --- Reset stable state immediately when finger is not on sensor ---
    // This ensures stale BPM/SpO2 values are never shown for a new finger
    // placement session. The firmware already resets on its side; the mobile
    // must mirror that to avoid blending an old stable value with new data.
    if (!packet.fingerDetected) {
      _stableBpm = null;
      _pendingBpm = null;
      _pendingBpmConfirm = 0;
      _stableSpo2 = null;
      _lastSpo2ValidAt = null;
    }

    // --- BPM smoothing ---
    final smoothedBpm = _applySmoothBpm(packet.heartRate, packet.hrValid);
    final bpmValid = smoothedBpm != null && smoothedBpm > 0;

    // --- SpO2 last-valid retention (10 second window, finger-gated) ---
    // Do NOT retain SpO2 when finger is absent: showing a stale value from
    // the previous session would be misleading.
    double spo2Value;
    bool spo2Valid;
    if (packet.fingerDetected && packet.spo2Valid && packet.spo2 > 0) {
      _stableSpo2 = packet.spo2;
      _lastSpo2ValidAt = DateTime.now();
      spo2Value = packet.spo2;
      spo2Valid = true;
    } else if (packet.fingerDetected &&
        _stableSpo2 != null &&
        _lastSpo2ValidAt != null &&
        DateTime.now().difference(_lastSpo2ValidAt!).inSeconds < 10) {
      spo2Value = _stableSpo2!;
      spo2Valid = true;
    } else {
      spo2Value = 0.0;
      spo2Valid = false;
    }

    // --- Local runtime risk score ---
    final localRisk = LocalRiskCalculator.calculate(
      fingerPresent: packet.fingerDetected,
      bpm: smoothedBpm ?? 0.0,
      bpmValid: bpmValid,
      spo2: spo2Value,
      spo2Valid: spo2Valid,
      movementPercent: _motionScoreEma * 100.0,
      signalQuality: packet.signalQuality,
    );

    return raw.copyWith(
      heartRate: bpmValid ? smoothedBpm : 0.0,
      heartRateValid: bpmValid,
      spo2: spo2Value,
      spo2Valid: spo2Valid,
      motionScore: _motionScoreEma,
      riskScore: localRisk,
    );
  }

  /// Applies EMA smoothing with large-jump confirmation (> 25 BPM).
  /// Returns the current stable BPM or null when no valid reading exists.
  double? _applySmoothBpm(double incoming, bool valid) {
    if (!valid || incoming <= 0) return null;

    final stable = _stableBpm;
    if (stable == null) {
      _stableBpm = incoming;
      return incoming;
    }

    final diff = (incoming - stable).abs();
    if (diff > 25.0) {
      // Large jump — require 2 consecutive similar readings to accept
      if (_pendingBpm != null && (incoming - _pendingBpm!).abs() < 15.0) {
        _pendingBpmConfirm++;
        if (_pendingBpmConfirm >= 2) {
          // Full replace — do NOT blend stale + incoming (that produces a
          // midpoint value that is wrong for both old and new BPM levels).
          _stableBpm = incoming;
          _pendingBpm = null;
          _pendingBpmConfirm = 0;
          return _stableBpm;
        }
      } else {
        _pendingBpm = incoming;
        _pendingBpmConfirm = 1;
      }
      return stable; // Keep showing last stable while confirming
    } else {
      // Normal variation — apply EMA (α = 0.3)
      _stableBpm = stable * 0.7 + incoming * 0.3;
      _pendingBpm = null;
      _pendingBpmConfirm = 0;
      return _stableBpm;
    }
  }
}
