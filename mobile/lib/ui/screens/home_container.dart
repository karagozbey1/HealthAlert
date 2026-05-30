import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import 'dashboard_screen.dart';
import 'health_assistant_screen.dart';
import 'live_monitor_screen.dart';
import 'history_screen.dart';
import 'settings_screen.dart';
class HomeContainer extends StatefulWidget {
  const HomeContainer({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<HomeContainer> createState() => _HomeContainerState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _HomeContainerState extends State<HomeContainer> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const DashboardScreen(),
    const LiveMonitorScreen(),
    const HealthAssistantScreen(),
    const HistoryScreen(),
    const SettingsScreen(),
  ];

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final hasActiveAlert = app.activeAlert != null;

    return Scaffold(
      extendBody: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          if (hasActiveAlert)
            IconButton(
              tooltip: 'Aktif Alarm',
              onPressed: () => Navigator.pushNamed(context, '/alert'),
              icon: Stack(
                children: const [
                  Icon(Icons.notification_important_outlined,
                      color: Colors.redAccent),
                  Positioned(
                    right: 0,
                    top: 0,
                    child: CircleAvatar(radius: 4, backgroundColor: Colors.red),
                  ),
                ],
              ),
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
          onTap: (index) => setState(() => _currentIndex = index),
          items: [
            const BottomNavigationBarItem(
              icon: Icon(Icons.dashboard_outlined),
              activeIcon: Icon(Icons.dashboard),
              label: 'Panel',
            ),
            const BottomNavigationBarItem(
              icon: Icon(Icons.monitor_heart_outlined),
              activeIcon: Icon(Icons.monitor_heart),
              label: 'Canlı İzleme',
            ),
            const BottomNavigationBarItem(
              icon: Icon(Icons.health_and_safety_outlined),
              activeIcon: Icon(Icons.health_and_safety),
              label: 'Asistan',
            ),
            const BottomNavigationBarItem(
              icon: Icon(Icons.history_outlined),
              activeIcon: Icon(Icons.history),
              label: 'Geçmiş',
            ),
            const BottomNavigationBarItem(
              icon: Icon(Icons.settings_outlined),
              activeIcon: Icon(Icons.settings),
              label: 'Ayarlar',
            ),
          ],
        ),
      ),
    );
  }
}
