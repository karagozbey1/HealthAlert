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
    final isValidBle = status.source != 'ble' || status.heartRateValid != false;
    final isStabilizing = status.source == 'ble' &&
        status.fingerPresent == true &&
        status.heartRateValid == false;
    final alert = status.source == 'ble' ? false : (hr > 100 || hr < 50);
    return LiveValueCard(
      title: 'Kalp Atışı',
      value: isValidBle ? hr.toStringAsFixed(0) : '--',
      unit: 'BPM',
      icon: Icons.favorite,
      color: alert ? AppTheme.critical : AppTheme.secondary,
      isAlert: alert,
      subtitle: isStabilizing ? 'Stabil oluyor...' : status.scenarioLabel,
    );
  }

  factory LiveValueCard.spo2(LiveStatus status) {
    final sp = status.spo2;
    final isValidBle = status.source != 'ble' || status.spo2Valid != false;
    final isStabilizing = status.source == 'ble' &&
        status.fingerPresent == true &&
        status.spo2Valid == false;
    final alert = status.source == 'ble' ? false : sp < 94;
    return LiveValueCard(
      title: 'Oksijen',
      value: isValidBle ? sp.toStringAsFixed(1) : '--',
      unit: '%',
      icon: Icons.air,
      color: alert ? AppTheme.critical : AppTheme.primary,
      isAlert: alert,
      subtitle: isStabilizing ? 'Stabil oluyor...' : null,
    );
  }

  factory LiveValueCard.riskScore(LiveStatus status) {
    final score = status.riskScore;
    final isBleMeasurement = status.source == 'ble';
    final hasValue =
        score > 0.0 && (!isBleMeasurement || status.fingerPresent == true);
    final alert = hasValue && score > 0.6;

    String? subtitle;
    if (isBleMeasurement) {
      if (hasValue) {
        final pct = score * 100;
        if (pct <= 20) {
          subtitle = 'Düşük';
        } else if (pct <= 50) {
          subtitle = 'Orta';
        } else if (pct <= 75) {
          subtitle = 'Yüksek';
        } else {
          subtitle = 'Kritik';
        }
      } else {
        subtitle = 'Parmak bekleniyor';
      }
    }

    return LiveValueCard(
      title: isBleMeasurement ? 'Canlı Risk' : 'Risk Skoru',
      value: hasValue ? (score * 100).toStringAsFixed(0) : '--',
      unit: hasValue ? '%' : '',
      icon: Icons.analytics_outlined,
      color: alert ? AppTheme.warning : AppTheme.success,
      isAlert: alert,
      subtitle: subtitle,
    );
  }

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
                style: const TextStyle(
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
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ),
            ],
          ),
          if (subtitle != null)
            Text(
              subtitle!,
              style: const TextStyle(color: Colors.white38, fontSize: 11),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
        ],
      ),
    );
  }
}
