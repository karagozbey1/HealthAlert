import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import 'ble_device_service.dart';
import 'api_client.dart';
import '../models/live_status.dart';

enum TransportType { none, ble, wifi }

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

  TransportType get activeTransport => _activeTransport;
  bool get wifiAvailable => _wifiAvailable;
  bool get autoFallbackEnabled => _autoFallbackEnabled;
  bool get isReceivingData => _lastDataTime != null &&
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

  void start() {
    debugPrint('[Transport] Starting transport orchestrator (mode: $transportMode)...');

    _connectivitySub?.cancel();
    _connectivitySub =
        Connectivity().onConnectivityChanged.listen((results) {
      _wifiAvailable = results.any((r) =>
          r == ConnectivityResult.wifi || r == ConnectivityResult.ethernet);
      notifyListeners();
    });

    Connectivity().checkConnectivity().then((results) {
      _wifiAvailable = results.any((r) =>
          r == ConnectivityResult.wifi || r == ConnectivityResult.ethernet);
    });

    switch (transportMode) {
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
  }

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

  void enableAutoFallback() {
    _autoFallbackEnabled = true;
    notifyListeners();
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    stop();
    _packetController.close();
    _statusController.close();
    super.dispose();
  }

  void _setTransport(TransportType type) {
    if (_activeTransport != type) {
      _activeTransport = type;
      debugPrint('[Transport] Active transport: ${type.name}');
      notifyListeners();
    }
  }

  void _startBle() {
    debugPrint('[Transport] Starting BLE scan...');
    bleService.startScan();

    _fallbackTimer?.cancel();
    if (_autoFallbackEnabled) {
      _fallbackTimer = Timer(const Duration(seconds: 16), () {
        if (!bleService.isConnected) {
          debugPrint('[Transport] BLE timeout → switching to Wi-Fi fallback');
          _startWifiFallback();
        }
      });
    }
  }

  void _startWifiFallback() {
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

  void _onBlePacket(BlePacket packet) {
    _blePackets++;
    _lastDataTime = DateTime.now();

    if (!_packetController.isClosed) {
      _packetController.add(packet);
    }

    final status = packet.toLiveStatus(userId);
    if (!_statusController.isClosed) {
      _statusController.add(status);
    }
  }
}
