import 'enums.dart';

/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class AppSettings {
  const AppSettings({
    required this.hrHighThreshold,
    required this.hrLowThreshold,
    required this.notificationsEnabled,
    required this.batteryMode,
    required this.dimBrightness,
    required this.backgroundMonitoring,
    required this.uploadIntervalMinutes,
  });

  final double hrHighThreshold;
  final double hrLowThreshold;
  final bool notificationsEnabled;
  final BatteryMode batteryMode;
  final bool dimBrightness;
  final bool backgroundMonitoring;
  final int uploadIntervalMinutes;

  static const AppSettings defaults = AppSettings(
    hrHighThreshold: 120,
    hrLowThreshold: 50,
    notificationsEnabled: true,
    batteryMode: BatteryMode.balanced,
    dimBrightness: false,
    backgroundMonitoring: true,
    uploadIntervalMinutes: 5,
  );

  /// Modelin seçilen alanları değişmiş yeni bir kopyasını üretir.
  AppSettings copyWith({
    double? hrHighThreshold,
    double? hrLowThreshold,
    bool? notificationsEnabled,
    BatteryMode? batteryMode,
    bool? dimBrightness,
    bool? backgroundMonitoring,
    int? uploadIntervalMinutes,
  }) {
    return AppSettings(
      hrHighThreshold: hrHighThreshold ?? this.hrHighThreshold,
      hrLowThreshold: hrLowThreshold ?? this.hrLowThreshold,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
      batteryMode: batteryMode ?? this.batteryMode,
      dimBrightness: dimBrightness ?? this.dimBrightness,
      backgroundMonitoring: backgroundMonitoring ?? this.backgroundMonitoring,
      uploadIntervalMinutes:
          uploadIntervalMinutes ?? this.uploadIntervalMinutes,
    );
  }

  /// Uygulama modelini API veya Firestore payload formatına dönüştürür.
  Map<String, dynamic> toJson() => {
        'hrHighThreshold': hrHighThreshold,
        'hrLowThreshold': hrLowThreshold,
        'notificationsEnabled': notificationsEnabled,
        'batteryMode': batteryMode.name,
        'dimBrightness': dimBrightness,
        'backgroundMonitoring': backgroundMonitoring,
        'uploadIntervalMinutes': uploadIntervalMinutes,
      };

  /// API, BLE veya Firestore verisini uygulama modeline dönüştürür.
  static AppSettings fromJson(Map<String, dynamic> json) {
    return AppSettings(
      hrHighThreshold: (json['hrHighThreshold'] as num?)?.toDouble() ??
          defaults.hrHighThreshold,
      hrLowThreshold: (json['hrLowThreshold'] as num?)?.toDouble() ??
          defaults.hrLowThreshold,
      notificationsEnabled: json['notificationsEnabled'] as bool? ??
          defaults.notificationsEnabled,
      batteryMode: BatteryMode.values.firstWhere(
        (e) => e.name == json['batteryMode'],
        orElse: () => defaults.batteryMode,
      ),
      dimBrightness: json['dimBrightness'] as bool? ?? defaults.dimBrightness,
      backgroundMonitoring: json['backgroundMonitoring'] as bool? ??
          defaults.backgroundMonitoring,
      uploadIntervalMinutes: json['uploadIntervalMinutes'] as int? ??
          defaults.uploadIntervalMinutes,
    );
  }
}
