import 'package:flutter/material.dart';

import '../health_assistant_screen.dart';
import 'relative_alerts_screen.dart';
import 'relative_dashboard_screen.dart';
import 'relative_history_screen.dart';
import 'relative_settings_screen.dart';
class RelativeHomeContainer extends StatefulWidget {
  const RelativeHomeContainer({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<RelativeHomeContainer> createState() => _RelativeHomeContainerState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _RelativeHomeContainerState extends State<RelativeHomeContainer> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const RelativeDashboardScreen(),
    const RelativeAlertsScreen(),
    const HealthAssistantScreen(),
    const RelativeHistoryScreen(),
    const RelativeSettingsScreen(),
  ];

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
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
                  Icon(Icons.family_restroom,
                      size: 14, color: Colors.greenAccent),
                  SizedBox(width: 6),
                  Text(
                    'Yakın',
                    style: TextStyle(
                      color: Colors.greenAccent,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
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
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.dashboard_outlined),
              activeIcon: Icon(Icons.dashboard),
              label: 'Panel',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.notifications_outlined),
              activeIcon: Icon(Icons.notifications),
              label: 'Uyarılar',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.health_and_safety_outlined),
              activeIcon: Icon(Icons.health_and_safety),
              label: 'Asistan',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.history_outlined),
              activeIcon: Icon(Icons.history),
              label: 'Geçmiş',
            ),
            BottomNavigationBarItem(
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
