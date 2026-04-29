import 'package:flutter/material.dart';
import '../../../core/state/app_scope.dart';
import '../health_assistant_screen.dart';
import '../login_screen.dart';
import 'relative_dashboard_screen.dart';
import 'relative_history_screen.dart';
import 'relative_settings_screen.dart';
import 'relative_generate_code_screen.dart';
import 'relative_alerts_screen.dart';

class RelativeHomeContainer extends StatefulWidget {
  const RelativeHomeContainer({super.key});

  @override
  State<RelativeHomeContainer> createState() => _RelativeHomeContainerState();
}

class _RelativeHomeContainerState extends State<RelativeHomeContainer> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const RelativeDashboardScreen(),
    const RelativeAlertsScreen(),
    const HealthAssistantScreen(),
    const RelativeHistoryScreen(),
    const RelativeSettingsScreen(),
  ];

  /// Widget ağacını oluşturur.
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
                color: Colors.green.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.greenAccent.withOpacity(0.4)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Icon(Icons.family_restroom, size: 14, color: Colors.greenAccent),
                  SizedBox(width: 6),
                    Text('Yakın',
                      style: TextStyle(
                          color: Colors.greenAccent, fontSize: 12, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Kod Gir',
            onPressed: () async {
              await Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const RelativeGenerateCodeScreen()));
              if (context.mounted) AppScope.of(context).loadMonitoredUsers();
            },
            icon: const Icon(Icons.link, color: Colors.greenAccent),
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
                label: 'Panel'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.notifications_outlined),
                activeIcon: Icon(Icons.notifications),
                label: 'Uyarılar'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.health_and_safety_outlined),
                activeIcon: Icon(Icons.health_and_safety),
                label: 'Asistan'),
            const BottomNavigationBarItem(
                icon: Icon(Icons.history_outlined),
                activeIcon: Icon(Icons.history),
                label: 'Geçmiş'),
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
