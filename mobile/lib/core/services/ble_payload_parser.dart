import 'dart:math' as math;

import '../models/live_status.dart';

const double _normalizedQualityMax = 1.0;
const double _percentQualityScale = 100.0;
const double _gyroDeadbandDps = 10.0;
const double _accDynamicDeadbandG = 0.04;
const double _stationaryAccLimitG = 0.22;
const double _stationaryMotionScale = 0.30;
const double _stationaryMotionMax = 0.07;
const double _accMotionScale = 120.0;
const double _gyroMotionScale = 0.8;
const double _motionPercentMax = 100.0;

/// Dinamik değeri sayıysa double değere çevirir, değilse null döndürür.
double? _numOrNull(dynamic value) => value is num ? value.toDouble() : null;

/// Dinamik BLE alanını güvenli int değere çevirir.
int _intValue(dynamic value, [int fallback = 0]) {
  if (value is bool) return value ? 1 : 0;
  if (value is num) return value.toInt();
  return fallback;
}

/// Dinamik BLE bayrak alanını güvenli bool değere çevirir.
bool _boolValue(dynamic value, [bool fallback = false]) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  return fallback;
}

/// Sinyal kalitesini 0 ile 1 aralığında normalize eder.
double _quality01(dynamic value) {
  final q = _numOrNull(value) ?? 0;
  if (q > _normalizedQualityMax) {
    return (q / _percentQualityScale)
        .clamp(0.0, _normalizedQualityMax)
        .toDouble();
  }
  return q.clamp(0.0, _normalizedQualityMax).toDouble();
}

/// Dinamik JSON alanını güvenli Map<String, dynamic> yapısına çevirir.
Map<String, dynamic> _mapValue(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, val) => MapEntry(key.toString(), val));
  }
  return const {};
}

/// Firmware BLE paketini mobil uygulamada kullanılan ölçüm modeline taşır.
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
    required this.redValue,
    required this.irValue,
    required this.signalQuality,
    required this.perfusionIndex,
    required this.rRatio,
    required this.irRangePercent,
    required this.accTotal,
    required this.gyroTotal,
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
  final int redValue;
  final int irValue;
  final double signalQuality;
  final double? perfusionIndex;
  final double? rRatio;
  final double? irRangePercent;
  final double accTotal;
  final double gyroTotal;
  final bool imuOk;
  final bool ppgOk;
  final bool hrValid;
  final bool spo2Valid;
  final bool fingerDetected;
  final String stateHint;

  factory BlePacket.fromJson(
    Map<String, dynamic> json, {
    String fallbackDeviceId = 'ha-esp32-001',
    int fallbackPacketSeq = 0,
  }) {
    if (json.containsKey('t') ||
        json.containsKey('bpm') ||
        json.containsKey('spo2e')) {
      return BlePacket.fromShortJson(
        json,
        fallbackDeviceId: fallbackDeviceId,
        fallbackPacketSeq: fallbackPacketSeq,
      );
    }
    if (json['imu'] is Map || json['ppg'] is Map) {
      return BlePacket.fromNestedJson(
        json,
        fallbackDeviceId: fallbackDeviceId,
        fallbackPacketSeq: fallbackPacketSeq,
      );
    }
    return BlePacket.fromLegacyFlatJson(
      json,
      fallbackDeviceId: fallbackDeviceId,
      fallbackPacketSeq: fallbackPacketSeq,
    );
  }

  factory BlePacket.fromShortJson(
    Map<String, dynamic> json, {
    required String fallbackDeviceId,
    required int fallbackPacketSeq,
  }) {
    final ax = _numOrNull(json['ax']) ?? 0;
    final ay = _numOrNull(json['ay']) ?? 0;
    final az = _numOrNull(json['az']) ?? 0;
    final gx = _numOrNull(json['gx']) ?? 0;
    final gy = _numOrNull(json['gy']) ?? 0;
    final gz = _numOrNull(json['gz']) ?? 0;

    return BlePacket(
      deviceId: json['device_id'] as String? ??
          json['id'] as String? ??
          fallbackDeviceId,
      timestampMs: _intValue(json['t'], DateTime.now().millisecondsSinceEpoch),
      mode: json['mode'] as String? ?? 'real',
      packetSeq: _intValue(json['seq'], fallbackPacketSeq),
      heartRate: _numOrNull(json['bpm']) ?? 0,
      spo2: _numOrNull(json['spo2e']) ?? 0,
      accelX: ax,
      accelY: ay,
      accelZ: az,
      gyroX: gx,
      gyroY: gy,
      gyroZ: gz,
      redValue: _intValue(json['red']),
      irValue: _intValue(json['ir']),
      signalQuality: _quality01(json['q']),
      perfusionIndex: _numOrNull(json['pi']),
      rRatio: _numOrNull(json['rr']),
      irRangePercent: _numOrNull(json['irg']),
      accTotal: _numOrNull(json['at']) ?? _vectorTotal(ax, ay, az),
      gyroTotal: _numOrNull(json['gt']) ?? _vectorTotal(gx, gy, gz),
      imuOk: true,
      ppgOk: _intValue(json['ir']) > 0 || _intValue(json['red']) > 0,
      hrValid: _boolValue(json['bv']),
      spo2Valid: _boolValue(json['sv']),
      fingerDetected: _boolValue(json['fp']),
      stateHint: json['state_hint'] as String? ?? 'ble_live',
    );
  }

  factory BlePacket.fromNestedJson(
    Map<String, dynamic> json, {
    required String fallbackDeviceId,
    required int fallbackPacketSeq,
  }) {
    final imu = _mapValue(json['imu']);
    final ppg = _mapValue(json['ppg']);
    final ax = _numOrNull(imu['acc_x']) ?? _numOrNull(imu['accel_x']) ?? 0;
    final ay = _numOrNull(imu['acc_y']) ?? _numOrNull(imu['accel_y']) ?? 0;
    final az = _numOrNull(imu['acc_z']) ?? _numOrNull(imu['accel_z']) ?? 0;
    final gx = _numOrNull(imu['gyro_x']) ?? 0;
    final gy = _numOrNull(imu['gyro_y']) ?? 0;
    final gz = _numOrNull(imu['gyro_z']) ?? 0;

    return BlePacket(
      deviceId: json['device_id'] as String? ?? fallbackDeviceId,
      timestampMs: _intValue(
          json['timestamp_ms'], DateTime.now().millisecondsSinceEpoch),
      mode: json['mode'] as String? ?? 'real',
      packetSeq: _intValue(json['packet_seq'], fallbackPacketSeq),
      heartRate: _numOrNull(json['heart_rate']) ?? 0,
      spo2: _numOrNull(json['spo2']) ?? 0,
      accelX: ax,
      accelY: ay,
      accelZ: az,
      gyroX: gx,
      gyroY: gy,
      gyroZ: gz,
      redValue: _intValue(ppg['red'] ?? json['red_value']),
      irValue: _intValue(ppg['ir'] ?? json['ir_value']),
      signalQuality: _quality01(json['signal_quality']),
      perfusionIndex: _numOrNull(json['pi_percent']),
      rRatio: _numOrNull(json['r_ratio']),
      irRangePercent: _numOrNull(json['ir_range_percent']),
      accTotal: _vectorTotal(ax, ay, az),
      gyroTotal: _vectorTotal(gx, gy, gz),
      imuOk: json['imu_ok'] as bool? ?? imu.isNotEmpty,
      ppgOk: json['ppg_ok'] as bool? ?? ppg.isNotEmpty,
      // Never infer validity from a non-null value — always require the
      // explicit hr_valid/spo2_valid flags.  Inferring "valid=true because
      // the field is present" caused 70-77% SpO2 values stored by earlier
      // firmware to appear as valid readings on the dashboard.
      hrValid: _boolValue(json['hr_valid']),
      spo2Valid: _boolValue(json['spo2_valid']),
      fingerDetected: json['finger_detected'] as bool? ?? false,
      stateHint: json['state_hint'] as String? ?? 'ble_live',
    );
  }

  factory BlePacket.fromLegacyFlatJson(
    Map<String, dynamic> json, {
    required String fallbackDeviceId,
    required int fallbackPacketSeq,
  }) {
    final ax = _numOrNull(json['accel_x']) ?? _numOrNull(json['ax']) ?? 0;
    final ay = _numOrNull(json['accel_y']) ?? _numOrNull(json['ay']) ?? 0;
    final az = _numOrNull(json['accel_z']) ?? _numOrNull(json['az']) ?? 0;
    final gx = _numOrNull(json['gyro_x']) ?? _numOrNull(json['gx']) ?? 0;
    final gy = _numOrNull(json['gyro_y']) ?? _numOrNull(json['gy']) ?? 0;
    final gz = _numOrNull(json['gyro_z']) ?? _numOrNull(json['gz']) ?? 0;

    return BlePacket(
      deviceId: json['device_id'] as String? ?? fallbackDeviceId,
      timestampMs: _intValue(
          json['timestamp_ms'], DateTime.now().millisecondsSinceEpoch),
      mode: json['mode'] as String? ?? 'real',
      packetSeq: _intValue(json['packet_seq'], fallbackPacketSeq),
      heartRate: _numOrNull(json['heart_rate']) ?? _numOrNull(json['bpm']) ?? 0,
      spo2: _numOrNull(json['spo2']) ?? _numOrNull(json['spo2e']) ?? 0,
      accelX: ax,
      accelY: ay,
      accelZ: az,
      gyroX: gx,
      gyroY: gy,
      gyroZ: gz,
      redValue: _intValue(json['red_value'] ?? json['red']),
      irValue: _intValue(json['ir_value'] ?? json['ir']),
      signalQuality: _quality01(json['signal_quality'] ?? json['q']),
      perfusionIndex: _numOrNull(json['pi_percent'] ?? json['pi']),
      rRatio: _numOrNull(json['r_ratio'] ?? json['rr']),
      irRangePercent: _numOrNull(json['ir_range_percent'] ?? json['irg']),
      accTotal: _numOrNull(json['at']) ?? _vectorTotal(ax, ay, az),
      gyroTotal: _numOrNull(json['gt']) ?? _vectorTotal(gx, gy, gz),
      imuOk: json['imu_ok'] as bool? ?? true,
      ppgOk: json['ppg_ok'] as bool? ?? true,
      // Same rule as fromNestedJson: never infer validity from a non-null value.
      hrValid: _boolValue(json['hr_valid'] ?? json['bv']),
      spo2Valid: _boolValue(json['spo2_valid'] ?? json['sv']),
      fingerDetected:
          json['finger_detected'] as bool? ?? _boolValue(json['fp']),
      stateHint: json['state_hint'] as String? ?? 'ble_live',
    );
  }

  /// Uygulama modelini API veya Firestore payload formatına dönüştürür.
  Map<String, dynamic> toJson() => {
        'device_id': deviceId,
        'timestamp_ms': timestampMs,
        'mode': mode == 'real' ? 'real' : 'mock',
        'packet_seq': packetSeq,
        'accel_x': accelX,
        'accel_y': accelY,
        'accel_z': accelZ,
        'gyro_x': gyroX,
        'gyro_y': gyroY,
        'gyro_z': gyroZ,
        'red_value': redValue,
        'ir_value': irValue,
        'heart_rate': heartRate,
        'spo2': spo2,
        'signal_quality': signalQuality,
        'pi_percent': perfusionIndex,
        'r_ratio': rRatio,
        'ir_range_percent': irRangePercent,
        'imu_ok': imuOk,
        'ppg_ok': ppgOk,
        'hr_valid': hrValid,
        'spo2_valid': spo2Valid,
        'finger_detected': fingerDetected,
        'state_hint': stateHint,
      };

  /// BLE telemetri paketini canlı sağlık durumu modeline dönüştürür.
  LiveStatus toLiveStatus(String userId) {
    // BLE packet only carries measurements. Personalized risk interpretation
    // must be done by backend/model/personalization layer.
    return LiveStatus(
      id: 'ble_$packetSeq',
      userId: userId,
      heartRate: hrValid ? heartRate : 0,
      spo2: spo2Valid ? spo2 : 0,
      motionScore: _computeMotionScore(
        accTotal,
        gyroTotal,
        imuOk: imuOk,
      ),
      riskScore: 0, // local risk computed by TransportOrchestrator
      scenario: 'ble_live',
      timestamp: DateTime.now(),
      signalQuality: signalQuality,
      fingerPresent: fingerDetected,
      heartRateValid: hrValid,
      spo2Valid: spo2Valid,
      accelX: accelX,
      accelY: accelY,
      accelZ: accelZ,
      gyroX: gyroX,
      gyroY: gyroY,
      gyroZ: gyroZ,
      accTotal: accTotal,
      gyroTotal: gyroTotal,
      irValue: irValue,
      redValue: redValue,
      perfusionIndex: perfusionIndex,
      rRatio: rRatio,
      irRangePercent: irRangePercent,
      source: 'ble',
    );
  }

  /// İvme ve jiroskop toplamlarından 0 ile 1 arasında hareket skoru hesaplar.
  static double _computeMotionScore(
    double accTotal,
    double gyroTotal, {
    required bool imuOk,
  }) {
    if (!imuOk || (accTotal == 0.0 && gyroTotal == 0.0)) return 0.0;

    final accDynamic =
        math.max(0.0, (accTotal - 1.0).abs() - _accDynamicDeadbandG);
    final gyroDynamic = math.max(0.0, gyroTotal - _gyroDeadbandDps);

    // Finger pressure can bias the static accelerometer total. With no
    // rotational energy, keep that low and avoid a sticky 20% display.
    if (gyroDynamic == 0.0 && accDynamic <= _stationaryAccLimitG) {
      return (accDynamic * _stationaryMotionScale)
          .clamp(0.0, _stationaryMotionMax)
          .toDouble();
    }

    final movementRaw =
        (accDynamic * _accMotionScale) + (gyroDynamic * _gyroMotionScale);
    return movementRaw.clamp(0.0, _motionPercentMax) / _motionPercentMax;
  }

  /// Üç eksenli sensör değerleri için vektör büyüklüğünü hesaplar.
  static double _vectorTotal(double x, double y, double z) {
    return math.sqrt((x * x) + (y * y) + (z * z));
  }
}
