import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';

class ModeBanner extends StatelessWidget {
  const ModeBanner({super.key});

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isLive = app.isBackendMode;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
      color: isLive ? const Color(0xFF1B5E20) : const Color(0xFF4A148C),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            isLive ? Icons.cloud_done : Icons.science,
            size: 14,
            color: Colors.white70,
          ),
          const SizedBox(width: 6),
          Text(
            isLive ? 'CANLI — Sunucu Bağlı' : 'DEMO MODU — Yerel Veri',
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }
}
