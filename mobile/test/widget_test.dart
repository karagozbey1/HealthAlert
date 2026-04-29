import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:mobile/core/repositories/local_store.dart';
import 'package:mobile/core/state/app_bootstrap.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Mock bootstrap initializes controller', () async {
    SharedPreferences.setMockInitialValues({});
    LocalStore.resetForTest();
    await LocalStore.clear();
    final controller = await buildMockAppController();
    await controller.initialize();
    expect(controller.initialized, true);
    expect(controller.settings.notificationsEnabled, true);
  });
}
