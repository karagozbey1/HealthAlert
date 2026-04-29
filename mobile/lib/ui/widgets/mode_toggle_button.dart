import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import '../theme/app_theme.dart';

class ModeToggleButton extends StatefulWidget {
  const ModeToggleButton({super.key});

  @override
  State<ModeToggleButton> createState() => _ModeToggleButtonState();
}

class _ModeToggleButtonState extends State<ModeToggleButton> {
  bool _switching = false;

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isLive = app.isBackendMode;

    return GestureDetector(
      onTap: _switching ? null : () => _showModeMenu(context, app),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: isLive
              ? AppTheme.success.withOpacity(0.15)
              : Colors.orangeAccent.withOpacity(0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isLive
                ? AppTheme.success.withOpacity(0.6)
                : Colors.orangeAccent.withOpacity(0.6),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_switching)
              SizedBox(
                width: 10,
                height: 10,
                child: CircularProgressIndicator(
                  strokeWidth: 1.5,
                  color: isLive ? AppTheme.success : Colors.orangeAccent,
                ),
              )
            else
              Icon(
                isLive
                    ? Icons.cloud_done_outlined
                    : Icons.cloud_off_outlined,
                size: 12,
                color: isLive ? AppTheme.success : Colors.orangeAccent,
              ),
            const SizedBox(width: 5),
            Text(
              isLive ? 'Canlı' : 'Demo',
              style: TextStyle(
                color: isLive ? AppTheme.success : Colors.orangeAccent,
                fontSize: 11,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(width: 3),
            Icon(
              Icons.arrow_drop_down,
              size: 14,
              color: isLive
                  ? AppTheme.success.withOpacity(0.7)
                  : Colors.orangeAccent.withOpacity(0.7),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showModeMenu(BuildContext context, dynamic app) async {
    final isLive = app.isBackendMode as bool;

    final result = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _ModeSwitchSheet(
        currentlyLive: isLive,
        backendUrl: app.backendUrl as String,
      ),
    );

    if (result == null || !mounted) return;

    if (result == 'live') {
      setState(() => _switching = true);
      final err = await app.switchToLive() as String?;
      if (!mounted) return;
      setState(() => _switching = false);
      if (err != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(err, style: const TextStyle(color: Colors.white)),
            backgroundColor: Colors.redAccent.withOpacity(0.9),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 4),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Canlı sunucu verisi kullanılıyor.',
                style: TextStyle(color: Colors.white)),
            backgroundColor: AppTheme.success.withOpacity(0.9),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } else if (result == 'demo') {
      app.switchToDemo();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Yerel demo verisi gösteriliyor.',
              style: TextStyle(color: Colors.white)),
          backgroundColor: Colors.orangeAccent.withOpacity(0.9),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }
}

class _ModeSwitchSheet extends StatelessWidget {
  final bool currentlyLive;
  final String backendUrl;

  const _ModeSwitchSheet({
    required this.currentlyLive,
    required this.backendUrl,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        border: Border.all(color: Colors.white12),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const Text('Veri Kaynağı',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(
              'Uygulamanın hangi veriden çalışacağını seçin.',
              style: TextStyle(color: Colors.white54, fontSize: 12),
            ),
            const SizedBox(height: 20),

            _ModeOptionTile(
              icon: Icons.cloud_done_outlined,
              color: AppTheme.success,
              title: 'Canlı Mod',
              subtitle: 'Canlı sunucu verisi kullanılıyor ($backendUrl)',
              selected: currentlyLive,
              onTap: () => Navigator.pop(context, 'live'),
            ),
            const SizedBox(height: 12),

            _ModeOptionTile(
              icon: Icons.cloud_off_outlined,
              color: Colors.orangeAccent,
              title: 'Demo Mod',
              subtitle: 'Yerel demo verisi gösteriliyor',
              selected: !currentlyLive,
              onTap: () => Navigator.pop(context, 'demo'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}

class _ModeOptionTile extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  const _ModeOptionTile({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: selected ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: selected ? color.withOpacity(0.12) : Colors.white.withOpacity(0.04),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected ? color.withOpacity(0.5) : Colors.white12,
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                          color: selected ? color : Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 14)),
                  const SizedBox(height: 2),
                  Text(subtitle,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 11)),
                ],
              ),
            ),
            if (selected)
              Icon(Icons.check_circle, color: color, size: 18)
            else
              const Icon(Icons.chevron_right, color: Colors.white24, size: 18),
          ],
        ),
      ),
    );
  }
}
