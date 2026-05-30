import 'package:flutter/material.dart';

import '../../../core/state/app_scope.dart';
import '../../../ui/theme/app_theme.dart';
import '../../../ui/widgets/glass_card.dart';

class WorkModeSettingsScreen extends StatefulWidget {
  const WorkModeSettingsScreen({super.key});

  @override
  State<WorkModeSettingsScreen> createState() => _WorkModeSettingsScreenState();
}

class _WorkModeSettingsScreenState extends State<WorkModeSettingsScreen> {
  Future<void> _switchMode({required bool live}) async {
    final app = AppScope.of(context);
    if (live) {
      final err = await app.switchToLive(url: app.backendUrl);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(err ?? 'Canlı izleme açıldı.'),
          backgroundColor: err == null ? AppTheme.success : Colors.redAccent,
        ),
      );
      return;
    }

    app.switchToDemo();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Demo gösterim açıldı.'),
        backgroundColor: Colors.orangeAccent,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isLive = app.isBackendMode;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Çalışma Modu'),
        leading: const BackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 8),
            GlassCard(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isLive ? 'Canlı İzleme' : 'Demo Gösterim',
                    style: TextStyle(
                      color: isLive ? AppTheme.success : Colors.orangeAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    isLive
                        ? 'Gerçek cihaz ve hasta verileriyle izleme yapılır.'
                        : 'Ürün tanıtımı için örnek hasta verileri gösterilir.',
                    style: const TextStyle(color: Colors.white54, fontSize: 13),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            _modeOption(
              selected: isLive,
              icon: Icons.monitor_heart_outlined,
              title: 'Canlı İzleme',
              subtitle: 'Hasta verileri güncel bağlantı üzerinden izlenir.',
              color: AppTheme.success,
              onTap: isLive ? null : () => _switchMode(live: true),
            ),
            const SizedBox(height: 10),
            _modeOption(
              selected: !isLive,
              icon: Icons.play_circle_outline,
              title: 'Demo Gösterim',
              subtitle:
                  'Sunum ve eğitim için güvenli örnek değerler kullanılır.',
              color: Colors.orangeAccent,
              onTap: !isLive ? null : () => _switchMode(live: false),
            ),
          ],
        ),
      ),
    );
  }

  Widget _modeOption({
    required bool selected,
    required IconData icon,
    required String title,
    required String subtitle,
    required Color color,
    required VoidCallback? onTap,
  }) {
    return GlassCard(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: color.withOpacity(selected ? 0.18 : 0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: color.withOpacity(selected ? 0.45 : 0.16),
                  ),
                ),
                child: Icon(icon, color: selected ? color : Colors.white38),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: selected ? color : Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style:
                          const TextStyle(color: Colors.white38, fontSize: 12),
                    ),
                  ],
                ),
              ),
              Icon(
                selected ? Icons.check_circle : Icons.radio_button_unchecked,
                color: selected ? color : Colors.white24,
                size: 22,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
