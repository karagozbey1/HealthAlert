import 'enums.dart';

class DeviceState {
  const DeviceState({
    required this.batteryPercent,
    required this.isConnected,
    required this.mode,
    required this.lastSync,
  });

  final int batteryPercent;
  final bool isConnected;
  final BatteryMode mode;
  final DateTime lastSync;

  DeviceState copyWith({
    int? batteryPercent,
    bool? isConnected,
    BatteryMode? mode,
    DateTime? lastSync,
  }) {
    return DeviceState(
      batteryPercent: batteryPercent ?? this.batteryPercent,
      isConnected: isConnected ?? this.isConnected,
      mode: mode ?? this.mode,
      lastSync: lastSync ?? this.lastSync,
    );
  }
}
