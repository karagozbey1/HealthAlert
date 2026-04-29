import 'package:flutter/material.dart';
import '../../core/models/live_status.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class LiveValueCard extends StatelessWidget {
  final String title;
  final String value;
  final String unit;
  final IconData icon;
  final Color color;
  final bool isAlert;
  final String? subtitle;

  const LiveValueCard({
    super.key,
    required this.title,
    required this.value,
    required this.unit,
    required this.icon,
    required this.color,
    this.isAlert = false,
    this.subtitle,
  });

  factory LiveValueCard.heartRate(LiveStatus status) {
    final hr = status.heartRate;
    final alert = hr != null && (hr > 100 || hr < 50);
    return LiveValueCard(
      title: 'Heart Rate',
      value: hr?.toStringAsFixed(0) ?? '--',
      unit: 'BPM',
      icon: Icons.favorite,
      color: alert ? AppTheme.critical : AppTheme.secondary,
      isAlert: alert,
      subtitle: status.scenarioLabel,
    );
  }

  factory LiveValueCard.spo2(LiveStatus status) {
    final sp = status.spo2;
    final alert = sp != null && sp < 94;
    return LiveValueCard(
      title: 'SpO₂',
      value: sp?.toStringAsFixed(1) ?? '--',
      unit: '%',
      icon: Icons.air,
      color: alert ? AppTheme.critical : AppTheme.primary,
      isAlert: alert,
    );
  }

  factory LiveValueCard.riskScore(LiveStatus status) {
    final score = status.riskScore;
    final alert = score != null && score > 0.6;
    return LiveValueCard(
      title: 'Risk Score',
      value: score != null ? (score * 100).toStringAsFixed(0) : '--',
      unit: '%',
      icon: Icons.analytics_outlined,
      color: alert ? AppTheme.warning : AppTheme.success,
      isAlert: alert,
    );
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return GlassCard(
      color: isAlert ? color.withOpacity(0.08) : null,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 18),
              const SizedBox(width: 8),
              Text(
                title.toUpperCase(),
                style: TextStyle(
                  color: color.withOpacity(0.8),
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1,
                ),
              ),
              if (isAlert) ...[
                const Spacer(),
                Icon(Icons.warning_amber_rounded, color: color, size: 14),
              ],
            ],
          ),
          const Spacer(),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                value,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  unit,
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ),
            ],
          ),
          if (subtitle != null)
            Text(
              subtitle!,
              style: TextStyle(color: Colors.white38, fontSize: 11),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
        ],
      ),
    );
  }
}
