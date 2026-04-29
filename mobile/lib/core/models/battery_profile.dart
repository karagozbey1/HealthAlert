import 'enums.dart';

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
