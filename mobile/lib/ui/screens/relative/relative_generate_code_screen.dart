import 'package:flutter/material.dart';
import '../self/redeem_code_screen.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class RelativeGenerateCodeScreen extends StatelessWidget {
  const RelativeGenerateCodeScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return const RedeemCodeScreen();
  }
}
