import 'package:flutter/material.dart';
import '../../core/services/health_assistant_service.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class TrendCard extends StatelessWidget {
  const TrendCard({super.key, required this.trend});

  final TrendAnalysis trend;

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    if (!trend.hasSufficientData) {
      return GlassCard(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            const Icon(Icons.trending_flat, size: 18, color: Colors.white30),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                trend.summary.isNotEmpty
                    ? trend.summary
                    : 'Trend analizi için yeterli veri bulunmuyor.',
                style: const TextStyle(color: Colors.white38, fontSize: 12),
              ),
            ),
          ],
        ),
      );
    }

    final color = _trendColor(trend.trendLabel);
    final icon = _trendIcon(trend.trendLabel);

    return GlassCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, size: 16, color: color),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'Trend: ',
                          style: TextStyle(
                            color: Colors.white54,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: color.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: color.withOpacity(0.4)),
                          ),
                          child: Text(
                            trend.trendLabelTr,
                            style: TextStyle(
                              color: color,
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      trend.summary,
                      style: const TextStyle(color: Colors.white60, fontSize: 12),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (trend.topConcern != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.warning.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.warning.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.priority_high, size: 14, color: AppTheme.warning),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Dikkat: ${trend.topConcern}',
                      style: const TextStyle(color: AppTheme.warning, fontSize: 11),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Color _trendColor(String label) {
    switch (label) {
      case 'artan_risk':
        return AppTheme.critical;
      case 'izlem_gerektiren':
        return AppTheme.warning;
      case 'iyilesiyor':
        return AppTheme.success;
      case 'stabil':
        return AppTheme.success;
      case 'olcum_kalitesi_dusuk':
        return Colors.orangeAccent;
      default:
        return Colors.white38;
    }
  }

  IconData _trendIcon(String label) {
    switch (label) {
      case 'artan_risk':
        return Icons.trending_up;
      case 'izlem_gerektiren':
        return Icons.trending_up;
      case 'iyilesiyor':
        return Icons.trending_down;
      case 'stabil':
        return Icons.trending_flat;
      case 'olcum_kalitesi_dusuk':
        return Icons.signal_cellular_connected_no_internet_0_bar;
      default:
        return Icons.help_outline;
    }
  }
}
