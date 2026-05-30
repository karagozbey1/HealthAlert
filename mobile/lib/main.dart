import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'core/models/enums.dart';
import 'core/state/app_bootstrap.dart';
import 'firebase_options.dart';
import 'core/state/app_controller.dart';
import 'core/state/app_scope.dart';
import 'ui/theme/app_theme.dart';
import 'ui/screens/login_screen.dart';
import 'ui/screens/register_screen.dart';
import 'ui/screens/home_container.dart';
import 'ui/screens/alert_screen.dart';
import 'ui/screens/post_event_monitor_screen.dart';
import 'ui/screens/relative/relative_home_container.dart';
import 'ui/screens/doctor/doctor_home_container.dart';

/// Firebase ve uygulama bağımlılıklarını hazırlayıp mobil uygulamayı başlatır.
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } catch (e) {
    debugPrint('[main] Firebase.initializeApp failed: $e');
  }
  final controller = await buildAppController(demoMode: false);
  await controller.initialize();
  runApp(MyApp(controller: controller));
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class MyApp extends StatelessWidget {
  const MyApp({super.key, required this.controller});

  final AppController controller;

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF000000),
      child: Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 420),
          decoration: BoxDecoration(
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.5),
                blurRadius: 20,
                spreadRadius: 5,
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius:
                kIsWeb ? BorderRadius.circular(20) : BorderRadius.zero,
            child: AppScope(
              controller: controller,
              child: MaterialApp(
                title: 'HealthAlert',
                debugShowCheckedModeBanner: false,
                theme: AppTheme.darkTheme,
                initialRoute: '/',
                routes: {
                  '/': (_) => const LoginScreen(),
                  '/register': (_) => const RegisterScreen(),
                  '/home': (_) => const RoleAwareHome(),
                  '/alert': (_) => const AlertScreen(type: AlertType.anomaly),
                  '/post-event': (_) => const PostEventMonitorScreen(),
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class RoleAwareHome extends StatelessWidget {
  const RoleAwareHome({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    switch (app.role) {
      case UserRole.relative:
        return const RelativeHomeContainer();
      case UserRole.doctor:
        return const DoctorHomeContainer();
      case UserRole.self:
        return const HomeContainer();
    }
  }
}
