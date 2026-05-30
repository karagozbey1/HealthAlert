import 'package:flutter/widgets.dart';

import 'app_controller.dart';

/// Uygulama genelinde AppController erişimini sağlayan InheritedNotifier katmanıdır.
class AppScope extends InheritedNotifier<AppController> {
  const AppScope({
    super.key,
    required AppController controller,
    required super.child,
  }) : super(notifier: controller);

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  static AppController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope not found in widget tree');
    return scope!.notifier!;
  }
}
