import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class MetricCard extends StatelessWidget {
  final String title;
  final String value;
  final String unit;
  final IconData icon;
  final Color accentColor;
  final Widget? trendGraph; // Placeholder for sparkline

  const MetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.unit,
    required this.icon,
    this.accentColor = AppTheme.primary,
    this.trendGraph,
  });

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Icon(icon, color: accentColor, size: 20),
              if (trendGraph != null)
                SizedBox(
                  width: 40,
                  height: 20,
                  child: trendGraph,
                ),
            ],
          ),
          const Spacer(),
          Text(
            value,
            style: AppTheme.darkTheme.textTheme.displayMedium,
          ),
          Row(
            children: [
              Text(
                unit,
                style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(width: 4),
              Text(
                title.toUpperCase(),
                style: AppTheme.darkTheme.textTheme.labelSmall,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
