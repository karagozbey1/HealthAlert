import 'enums.dart';

/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class BatteryProfile {
  const BatteryProfile({
    required this.mode,
    required this.title,
    required this.description,
  });

  final BatteryMode mode;
  final String title;
  final String description;
}
