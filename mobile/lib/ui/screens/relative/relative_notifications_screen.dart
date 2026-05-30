import 'package:flutter/material.dart';
import '../notifications_screen.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class RelativeNotificationsScreen extends StatelessWidget {
  const RelativeNotificationsScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) => const NotificationsScreen();
}
