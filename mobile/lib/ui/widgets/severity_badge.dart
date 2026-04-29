import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../theme/app_theme.dart';

class SeverityBadge extends StatelessWidget {
  final AlertSeverity severity;
  final bool compact;

  const SeverityBadge({super.key, required this.severity, this.compact = false});

  Color get _color {
    switch (severity) {
      case AlertSeverity.critical:
        return AppTheme.critical;
      case AlertSeverity.warning:
        return AppTheme.warning;
      case AlertSeverity.watch:
        return AppTheme.primary;
      case AlertSeverity.normal:
        return AppTheme.success;
    }
  }

  String get _label {
    switch (severity) {
      case AlertSeverity.critical:
        return 'KRİTİK';
      case AlertSeverity.warning:
        return 'UYARI';
      case AlertSeverity.watch:
        return 'İZLE';
      case AlertSeverity.normal:
        return 'NORMAL';
    }
  }

  IconData get _icon {
    switch (severity) {
      case AlertSeverity.critical:
        return Icons.dangerous_outlined;
      case AlertSeverity.warning:
        return Icons.warning_amber_rounded;
      case AlertSeverity.watch:
        return Icons.visibility_outlined;
      case AlertSeverity.normal:
        return Icons.check_circle_outline;
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 12,
        vertical: compact ? 3 : 5,
      ),
      decoration: BoxDecoration(
        color: _color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _color.withOpacity(0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_icon, size: compact ? 10 : 12, color: _color),
          const SizedBox(width: 4),
          Text(
            _label,
            style: TextStyle(
              color: _color,
              fontSize: compact ? 9 : 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.8,
            ),
          ),
        ],
      ),
    );
  }
}
