import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';
import 'package:permission_handler/permission_handler.dart';

import 'ble_payload_parser.dart';

export 'ble_payload_parser.dart' show BlePacket;

const _kServiceUuid = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const _kTelemetryCharUuid = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
enum BleConnectionState {
  disconnected,
  scanning,
  connecting,
  connected,
  error,
}

/// Mobil cihazın BLE tarama, bağlantı ve telemetri akışını yönetir.
class BleDeviceService extends ChangeNotifier {
  BleDeviceService({FlutterReactiveBle? reactiveBle})
      : _ble = reactiveBle ?? _createBle();

  final FlutterReactiveBle? _ble;

  /// Bu servis dosyasındaki canlı izleme veya destek adımını yürütür.
  static FlutterReactiveBle? _createBle() {
    if (kIsWeb) return null;
    if (!Platform.isAndroid && !Platform.isIOS) {
      return null;
    }
    return FlutterReactiveBle();
  }

  BleConnectionState _state = BleConnectionState.disconnected;
  StreamSubscription<DiscoveredDevice>? _scanSub;
  StreamSubscription<ConnectionStateUpdate>? _connectionSub;
  StreamSubscription<List<int>>? _telemetrySub;

  String? _connectedDeviceId;
  String? _connectedDeviceName;
  int _packetsReceived = 0;
  DateTime? _lastPacketTime;
  String _partialJson = '';

  final _packetController = StreamController<BlePacket>.broadcast();

  BleConnectionState get state => _state;
  bool get isConnected => _state == BleConnectionState.connected;
  String? get connectedDeviceId => _connectedDeviceId;
  String? get connectedDeviceName => _connectedDeviceName;
  int get packetsReceived => _packetsReceived;
  DateTime? get lastPacketTime => _lastPacketTime;
  Stream<BlePacket> get packetStream => _packetController.stream;

  /// Yakındaki BLE cihazlarını bulmak için tarama akışını başlatır.
  void startScan() {
    unawaited(_startScan());
  }

  /// BLE izinlerini kontrol edip platform taramasını çalıştırır.
  Future<void> _startScan() async {
    if (_ble == null) {
      debugPrint('[BLE] BLE scanning is unavailable on this platform.');
      _setState(BleConnectionState.disconnected);
      return;
    }

    if (_state == BleConnectionState.scanning) return;

    final permissionsOk = await _ensureBlePermissions();
    if (!permissionsOk) {
      debugPrint('[BLE] Required Bluetooth permissions were not granted.');
      _setState(BleConnectionState.error);
      return;
    }

    _setState(BleConnectionState.scanning);
    debugPrint('[BLE] Starting scan for service $_kServiceUuid');

    _scanSub?.cancel();
    _scanSub = _ble!.scanForDevices(
      withServices: [Uuid.parse(_kServiceUuid)],
      scanMode: ScanMode.lowLatency,
    ).listen(
      (device) {
        debugPrint('[BLE] Found device: ${device.name} (${device.id})');
        stopScan();
        connectToDevice(device.id, device.name);
      },
      onError: (Object error) {
        debugPrint('[BLE] Scan error: $error');
        _setState(BleConnectionState.error);
      },
    );

    Future.delayed(const Duration(seconds: 15), () {
      if (_state == BleConnectionState.scanning) {
        stopScan();
        _setState(BleConnectionState.disconnected);
      }
    });
  }

  /// Devam eden BLE cihaz taramasını durdurur.
  void stopScan() {
    _scanSub?.cancel();
    _scanSub = null;
    if (_state == BleConnectionState.scanning) {
      _setState(BleConnectionState.disconnected);
    }
  }

  /// Seçilen BLE cihazına bağlanma akışını başlatır.
  void connectToDevice(String deviceId, String deviceName) {
    if (_ble == null) {
      debugPrint('[BLE] BLE connection is unavailable on this platform.');
      _setState(BleConnectionState.disconnected);
      return;
    }

    _setState(BleConnectionState.connecting);
    debugPrint('[BLE] Connecting to $deviceName ($deviceId)...');

    _connectionSub?.cancel();
    _connectionSub = _ble!
        .connectToDevice(
      id: deviceId,
      connectionTimeout: const Duration(seconds: 10),
    )
        .listen(
      (update) {
        switch (update.connectionState) {
          case DeviceConnectionState.connected:
            debugPrint('[BLE] Connected to $deviceName');
            _connectedDeviceId = deviceId;
            _connectedDeviceName =
                deviceName.isEmpty ? 'HealthAlert' : deviceName;
            _setState(BleConnectionState.connected);
            unawaited(_prepareConnection(deviceId));
            break;
          case DeviceConnectionState.disconnected:
            debugPrint('[BLE] Disconnected from $deviceName');
            _connectedDeviceId = null;
            _connectedDeviceName = null;
            _partialJson = '';
            _telemetrySub?.cancel();
            _telemetrySub = null;
            _setState(BleConnectionState.disconnected);
            break;
          case DeviceConnectionState.connecting:
            _setState(BleConnectionState.connecting);
            break;
          case DeviceConnectionState.disconnecting:
            break;
        }
      },
      onError: (Object error) {
        debugPrint('[BLE] Connection error: $error');
        _connectedDeviceId = null;
        _connectedDeviceName = null;
        _setState(BleConnectionState.error);
      },
    );
  }

  /// Aktif BLE bağlantısını ve telemetri aboneliğini kapatır.
  void disconnect() {
    _telemetrySub?.cancel();
    _telemetrySub = null;
    _connectionSub?.cancel();
    _connectionSub = null;
    _connectedDeviceId = null;
    _connectedDeviceName = null;
    _partialJson = '';
    _setState(BleConnectionState.disconnected);
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _scanSub?.cancel();
    _connectionSub?.cancel();
    _telemetrySub?.cancel();
    _packetController.close();
    super.dispose();
  }

  /// BLE bağlantı durumunu güncelleyip dinleyicileri bilgilendirir.
  void _setState(BleConnectionState newState) {
    if (_state != newState) {
      _state = newState;
      notifyListeners();
    }
  }

  /// BLE tarama ve bağlantı izinlerinin verilip verilmediğini kontrol eder.
  Future<bool> _ensureBlePermissions() async {
    if (kIsWeb) return false;

    if (defaultTargetPlatform != TargetPlatform.android &&
        defaultTargetPlatform != TargetPlatform.iOS) {
      return true;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      final statuses = await [
        Permission.bluetoothScan,
        Permission.bluetoothConnect,
        Permission.locationWhenInUse,
      ].request();

      final scanGranted = statuses[Permission.bluetoothScan]?.isGranted ?? true;
      final connectGranted =
          statuses[Permission.bluetoothConnect]?.isGranted ?? true;
      final legacyLocationGranted =
          statuses[Permission.locationWhenInUse]?.isGranted ?? true;

      return connectGranted && (scanGranted || legacyLocationGranted);
    }

    return true;
  }

  /// BLE cihaz bağlantısını kurup telemetri aboneliğini hazırlar.
  Future<void> _prepareConnection(String deviceId) async {
    if (_ble == null) return;

    if (defaultTargetPlatform == TargetPlatform.android) {
      try {
        final mtu = await _ble!.requestMtu(deviceId: deviceId, mtu: 247);
        debugPrint('[BLE] Negotiated MTU: $mtu');
      } catch (error) {
        debugPrint('[BLE] MTU request failed, using default MTU: $error');
      }
    }

    _subscribeToTelemetry(deviceId);
  }

  /// BLE telemetri karakteristiğine dinleyici bağlar.
  void _subscribeToTelemetry(String deviceId) {
    if (_ble == null) return;

    final characteristic = QualifiedCharacteristic(
      characteristicId: Uuid.parse(_kTelemetryCharUuid),
      serviceId: Uuid.parse(_kServiceUuid),
      deviceId: deviceId,
    );

    debugPrint('[BLE] Subscribing to telemetry notifications...');
    _telemetrySub?.cancel();
    _telemetrySub = _ble!.subscribeToCharacteristic(characteristic).listen(
      _onTelemetryData,
      onError: (Object error) {
        debugPrint('[BLE] Telemetry subscription error: $error');
      },
    );
  }

  /// BLE karakteristiğinden gelen ham byte verisini satırlara ayırır.
  void _onTelemetryData(List<int> data) {
    try {
      final chunk = utf8.decode(data, allowMalformed: true).trim();
      final packet = _parsePacket(chunk);
      if (packet == null) return;

      _packetsReceived++;
      _lastPacketTime = DateTime.now();
      if (!_packetController.isClosed) {
        _packetController.add(packet);
      }
    } catch (e) {
      debugPrint('[BLE] Failed to parse telemetry: $e');
    }
  }

  /// BLE satırından JSON telemetri paketi üretmeye çalışır.
  BlePacket? _parsePacket(String chunk) {
    if (chunk.isEmpty) return null;

    final direct = _tryParseJson(chunk);
    if (direct != null) return direct;

    _partialJson += chunk;
    final buffered = _tryParseJson(_partialJson);
    if (buffered != null) {
      _partialJson = '';
      return buffered;
    }

    if (_partialJson.length > 1024 || chunk.startsWith('{')) {
      _partialJson = chunk;
    }
    return null;
  }

  /// Ham metni JSON BLE paketine güvenli şekilde dönüştürür.
  BlePacket? _tryParseJson(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return null;
      return BlePacket.fromJson(
        decoded,
        fallbackPacketSeq: _packetsReceived + 1,
      );
    } catch (error) {
      debugPrint('[BleDeviceService] Telemetry JSON parse failed: $error');
      return null;
    }
  }
}
