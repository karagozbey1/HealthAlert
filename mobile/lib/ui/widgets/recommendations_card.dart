import 'package:flutter/material.dart';
import '../../core/models/live_status.dart';
import '../../core/services/recommendation_service.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class RecommendationsCard extends StatelessWidget {
  const RecommendationsCard({super.key, required this.live});

  final LiveStatus? live;

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final service = RecommendationService();
    final recs = service.forLiveStatus(live);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.tips_and_updates_outlined,
                color: Colors.amberAccent, size: 18),
            const SizedBox(width: 8),
            Text(
              'Öneriler',
              style: AppTheme.darkTheme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ...recs.map((r) => _RecTile(rec: r)),
      ],
    );
  }
}

class _RecTile extends StatelessWidget {
  const _RecTile({required this.rec});

  final Recommendation rec;

  @override
  Widget build(BuildContext context) {
    final Color borderColor;
    final Color iconColor;
    final IconData icon;

    switch (rec.urgency) {
      case RecommendationUrgency.critical:
        borderColor = AppTheme.critical;
        iconColor = AppTheme.critical;
        icon = Icons.dangerous_outlined;
        break;
      case RecommendationUrgency.warning:
        borderColor = AppTheme.warning;
        iconColor = AppTheme.warning;
        icon = Icons.warning_amber_rounded;
        break;
      case RecommendationUrgency.info:
        borderColor = AppTheme.primary;
        iconColor = AppTheme.primary;
        icon = Icons.info_outline;
        break;
      default:
        borderColor = AppTheme.success;
        iconColor = AppTheme.success;
        icon = Icons.check_circle_outline;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              margin: const EdgeInsets.only(top: 1, right: 12),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: borderColor.withOpacity(0.12),
                border: Border.all(color: borderColor.withOpacity(0.4)),
              ),
              child: Icon(icon, color: iconColor, size: 16),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    rec.title,
                    style: TextStyle(
                      color: iconColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    rec.detail,
                    style: const TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const Icon(Icons.arrow_right, size: 14, color: Colors.white30),
                      const SizedBox(width: 2),
                      Expanded(
                        child: Text(
                          rec.action,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 12,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
