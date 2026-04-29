import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';

import '../models/live_status.dart';

const _kServiceUuid = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const _kTelemetryCharUuid = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';
const _kDeviceInfoCharUuid = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';

class BlePacket {
  const BlePacket({
    required this.deviceId,
    required this.timestampMs,
    required this.mode,
    required this.packetSeq,
    required this.heartRate,
    required this.spo2,
    required this.accelX,
    required this.accelY,
    required this.accelZ,
    required this.gyroX,
    required this.gyroY,
    required this.gyroZ,
    required this.signalQuality,
    required this.imuOk,
    required this.ppgOk,
    required this.hrValid,
    required this.spo2Valid,
    required this.fingerDetected,
    required this.stateHint,
  });

  final String deviceId;
  final int timestampMs;
  final String mode;
  final int packetSeq;
  final double heartRate;
  final double spo2;
  final double accelX;
  final double accelY;
  final double accelZ;
  final double gyroX;
  final double gyroY;
  final double gyroZ;
  final double signalQuality;
  final bool imuOk;
  final bool ppgOk;
  final bool hrValid;
  final bool spo2Valid;
  final bool fingerDetected;
  final String stateHint;

  factory BlePacket.fromJson(Map<String, dynamic> json) {
    return BlePacket(
      deviceId: json['device_id'] as String? ?? '',
      timestampMs: (json['timestamp_ms'] as num?)?.toInt() ?? 0,
      mode: json['mode'] as String? ?? 'unknown',
      packetSeq: (json['packet_seq'] as num?)?.toInt() ?? 0,
      heartRate: (json['heart_rate'] as num?)?.toDouble() ?? 0,
      spo2: (json['spo2'] as num?)?.toDouble() ?? 0,
      accelX: (json['accel_x'] as num?)?.toDouble() ?? 0,
      accelY: (json['accel_y'] as num?)?.toDouble() ?? 0,
      accelZ: (json['accel_z'] as num?)?.toDouble() ?? 0,
      gyroX: (json['gyro_x'] as num?)?.toDouble() ?? 0,
      gyroY: (json['gyro_y'] as num?)?.toDouble() ?? 0,
      gyroZ: (json['gyro_z'] as num?)?.toDouble() ?? 0,
      signalQuality: (json['signal_quality'] as num?)?.toDouble() ?? 0,
      imuOk: json['imu_ok'] as bool? ?? false,
      ppgOk: json['ppg_ok'] as bool? ?? false,
      hrValid: json['hr_valid'] as bool? ?? false,
      spo2Valid: json['spo2_valid'] as bool? ?? false,
      fingerDetected: json['finger_detected'] as bool? ?? false,
      stateHint: json['state_hint'] as String? ?? 'unknown',
    );
  }

  Map<String, dynamic> toJson() => {
        'device_id': deviceId,
        'timestamp_ms': timestampMs,
        'mode': mode,
        'packet_seq': packetSeq,
        'heart_rate': heartRate,
        'spo2': spo2,
        'accel_x': accelX,
        'accel_y': accelY,
        'accel_z': accelZ,
        'gyro_x': gyroX,
        'gyro_y': gyroY,
        'gyro_z': gyroZ,
        'signal_quality': signalQuality,
        'imu_ok': imuOk,
        'ppg_ok': ppgOk,
        'hr_valid': hrValid,
        'spo2_valid': spo2Valid,
        'finger_detected': fingerDetected,
        'state_hint': stateHint,
      };

  LiveStatus toLiveStatus(String userId) {
    final motionScore = _computeMotionScore();
    final riskScore = _computeRiskScore(motionScore);
    return LiveStatus(
      id: 'ble_${packetSeq}',
      userId: userId,
      heartRate: heartRate,
      spo2: spo2,
      motionScore: motionScore,
      riskScore: riskScore,
      scenario: stateHint,
      timestamp: DateTime.now(),
    );
  }

  double _computeMotionScore() {
    final accelMag =
        (accelX * accelX + accelY * accelY + accelZ * accelZ);
    final accelDev = (accelMag - 1.0).abs(); // 1g is rest
    final gyroMag =
        (gyroX * gyroX + gyroY * gyroY + gyroZ * gyroZ);
    return (accelDev * 0.6 + (gyroMag / 250.0) * 0.4).clamp(0.0, 1.0);
  }

  double _computeRiskScore(double motionScore) {
    double risk = 0.0;
    if (hrValid) {
      if (heartRate > 120) risk += 0.3;
      else if (heartRate > 100) risk += 0.15;
      else if (heartRate < 50) risk += 0.25;
    }
    if (spo2Valid) {
      if (spo2 < 90) risk += 0.4;
      else if (spo2 < 94) risk += 0.2;
    }
    risk += motionScore * 0.3;
    return risk.clamp(0.0, 1.0);
  }
}

enum BleConnectionState {
  disconnected,
  scanning,
  connecting,
  connected,
  error,
}

class BleDeviceService extends ChangeNotifier {
  BleDeviceService();

  final FlutterReactiveBle? _ble = kIsWeb ? null : FlutterReactiveBle();

  BleConnectionState _state = BleConnectionState.disconnected;
  StreamSubscription<DiscoveredDevice>? _scanSub;
  StreamSubscription<ConnectionStateUpdate>? _connectionSub;
  StreamSubscription<List<int>>? _telemetrySub;

  String? _connectedDeviceId;
  String? _connectedDeviceName;
  int _packetsReceived = 0;
  DateTime? _lastPacketTime;

  final _packetController = StreamController<BlePacket>.broadcast();

  BleConnectionState get state => _state;
  bool get isConnected => _state == BleConnectionState.connected;
  String? get connectedDeviceId => _connectedDeviceId;
  String? get connectedDeviceName => _connectedDeviceName;
  int get packetsReceived => _packetsReceived;
  DateTime? get lastPacketTime => _lastPacketTime;
  Stream<BlePacket> get packetStream => _packetController.stream;

  void startScan() {
    if (_ble == null) {
      debugPrint('[BLE] Web platform detected; BLE scanning is unavailable.');
      _setState(BleConnectionState.disconnected);
      return;
    }

    if (_state == BleConnectionState.scanning) return;

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

  void stopScan() {
    _scanSub?.cancel();
    _scanSub = null;
    if (_state == BleConnectionState.scanning) {
      _setState(BleConnectionState.disconnected);
    }
  }

  void connectToDevice(String deviceId, String deviceName) {
    if (_ble == null) {
      debugPrint('[BLE] Web platform detected; BLE connection is unavailable.');
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
            _connectedDeviceName = deviceName;
            _setState(BleConnectionState.connected);
            _subscribeToTelemetry(deviceId);
            break;
          case DeviceConnectionState.disconnected:
            debugPrint('[BLE] Disconnected from $deviceName');
            _connectedDeviceId = null;
            _connectedDeviceName = null;
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

  void disconnect() {
    _telemetrySub?.cancel();
    _telemetrySub = null;
    _connectionSub?.cancel();
    _connectionSub = null;
    _connectedDeviceId = null;
    _connectedDeviceName = null;
    _setState(BleConnectionState.disconnected);
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _scanSub?.cancel();
    _connectionSub?.cancel();
    _telemetrySub?.cancel();
    _packetController.close();
    super.dispose();
  }

  void _setState(BleConnectionState newState) {
    if (_state != newState) {
      _state = newState;
      notifyListeners();
    }
  }

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
      (data) {
        _onTelemetryData(data);
      },
      onError: (Object error) {
        debugPrint('[BLE] Telemetry subscription error: $error');
      },
    );
  }

  void _onTelemetryData(List<int> data) {
    try {
      final jsonStr = utf8.decode(data);
      final json = jsonDecode(jsonStr) as Map<String, dynamic>;
      final packet = BlePacket.fromJson(json);
      _packetsReceived++;
      _lastPacketTime = DateTime.now();
      if (!_packetController.isClosed) {
        _packetController.add(packet);
      }
    } catch (e) {
      debugPrint('[BLE] Failed to parse telemetry: $e');
    }
  }
}
