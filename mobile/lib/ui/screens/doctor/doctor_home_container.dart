import 'package:flutter/material.dart';
import '../../../core/state/app_scope.dart';
import '../health_assistant_screen.dart';
import '../login_screen.dart';
import 'doctor_alerts_screen.dart';
import 'doctor_dashboard_screen.dart';
import 'doctor_overview_screen.dart';
import 'doctor_settings_screen.dart';
import 'doctor_generate_code_screen.dart';

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class DoctorHomeContainer extends StatefulWidget {
  const DoctorHomeContainer({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<DoctorHomeContainer> createState() => _DoctorHomeContainerState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _DoctorHomeContainerState extends State<DoctorHomeContainer> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const DoctorOverviewScreen(),
    const DoctorDashboardScreen(),
    const HealthAssistantScreen(),
    const DoctorAlertsScreen(),
    const DoctorSettingsScreen(),
  ];

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);

    return Scaffold(
      extendBody: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.amber.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.amberAccent.withOpacity(0.4)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Icon(Icons.medical_services,
                      size: 14, color: Colors.amberAccent),
                  SizedBox(width: 6),
                  Text('Doktor',
                      style: TextStyle(
                          color: Colors.amberAccent,
                          fontSize: 12,
                          fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Kod Gir',
            onPressed: () async {
              await Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const DoctorGenerateCodeScreen()));
              if (context.mounted) AppScope.of(context).loadMonitoredUsers();
            },
            icon: const Icon(Icons.link, color: Colors.amberAccent),
          ),
          IconButton(
            tooltip: 'Çıkış yap',
            onPressed: () async {
              await app.logout();
              if (!context.mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (_) => false,
              );
            },
            icon: const Icon(Icons.logout_outlined),
          ),
        ],
      ),
      body: _screens[_currentIndex],
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              blurRadius: 20,
              offset: const Offset(0, -5),
            ),
          ],
        ),
        child: BottomNavigationBar(
          type: BottomNavigationBarType.fixed,
          currentIndex: _currentIndex,
          onTap: (i) => setState(() => _currentIndex = i),
          items: [
            const BottomNavigationBarItem(
                icon: Icon(Icons.dashboard_outlined),
                activeIcon: Icon(Icons.dashboard),
                label: 'Ana Panel'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.people_outlined),
                activeIcon: Icon(Icons.people),
                label: 'Hastalar'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.health_and_safety_outlined),
                activeIcon: Icon(Icons.health_and_safety),
                label: 'Asistan'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.notification_important_outlined),
                activeIcon: Icon(Icons.notification_important),
                label: 'Uyarılar'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.settings_outlined),
                activeIcon: Icon(Icons.settings),
                label: 'Ayarlar'),
          ],
        ),
      ),
    );
  }
}
