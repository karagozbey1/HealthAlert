import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/repositories/local_store.dart';
import 'package:mobile/core/repositories/mock_repositories.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Settings persistence', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      LocalStore.resetForTest();
    });

    test('saves and reloads app settings', () async {
      await LocalStore.clear();
      final repo = MockSettingsRepository();

      final initial = await repo.getSettings();
      expect(initial.hrHighThreshold, 120);

      final updated = initial.copyWith(
        hrHighThreshold: 130,
        notificationsEnabled: false,
        batteryMode: BatteryMode.saver,
      );
      await repo.saveSettings(updated);

      final reloaded = await repo.getSettings();
      expect(reloaded.hrHighThreshold, 130);
      expect(reloaded.notificationsEnabled, false);
      expect(reloaded.batteryMode, BatteryMode.saver);
    });
  });
}
