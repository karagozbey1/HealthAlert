import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/services/recommendation_service.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/gradient_button.dart';
class HealthStatusScreen extends StatelessWidget {
  const HealthStatusScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final anomalies = app.anomalies;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text("Sağlık Durumları"),
        backgroundColor: Colors.transparent,
      ),
      body: anomalies.isEmpty
          ? Center(
              child: Text(
                app.isBackendMode
                    ? 'Kayıtlı anomali bulunamadı.\nVeri akışı başladığında anomaliler burada görünecek.'
                    : 'Kayıtlı anomali bulunamadı.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white38),
              ),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: anomalies
                  .map(
                    (a) => _buildStatusCard(
                      context,
                      '${a.metric} anomalisi',
                      _severityLabel(a.severity),
                      _severityColor(a.severity),
                      a.detectedAt.toLocal().toString().substring(0, 16),
                      '${a.summary} (değer: ${a.value.toStringAsFixed(1)} ${a.unit})',
                      RecommendationService().forSeverity(a.severity),
                    ),
                  )
                  .toList(),
            ),
    );
  }

  /// Duruma göre ekranda kullanılacak rengi belirler.
  Color _severityColor(AlertSeverity severity) {
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

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  String _severityLabel(AlertSeverity severity) {
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
  Widget _buildStatusCard(
    BuildContext context,
    String title,
    String severityLabel,
    Color severityColor,
    String time,
    String description,
    List<String> recommendations,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: GlassCard(
        onTap: () =>
            _showDetailSheet(context, title, severityColor, recommendations),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: AppTheme.darkTheme.textTheme.titleLarge?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: severityColor.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: severityColor.withOpacity(0.5)),
                  ),
                  child: Text(
                    severityLabel,
                    style: TextStyle(
                      color: severityColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              time,
              style: AppTheme.darkTheme.textTheme.labelSmall,
            ),
            const SizedBox(height: 12),
            Text(
              description,
              style: AppTheme.darkTheme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  "Önerileri Gör",
                  style: TextStyle(
                      color: AppTheme.primary, fontWeight: FontWeight.bold),
                ),
                const SizedBox(width: 4),
                const Icon(Icons.arrow_forward,
                    color: AppTheme.primary, size: 16),
              ],
            ),
          ],
        ),
      ),
    );
  }
  void _showDetailSheet(BuildContext context, String title, Color color,
      List<String> recommendations) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        maxChildSize: 0.9,
        minChildSize: 0.5,
        builder: (_, controller) => Container(
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(30)),
            boxShadow: [
              BoxShadow(color: Colors.black.withOpacity(0.5), blurRadius: 20),
            ],
          ),
          child: Column(
            children: [
              const SizedBox(height: 16),
              Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                      color: Colors.grey[700],
                      borderRadius: BorderRadius.circular(2))),
              const SizedBox(height: 24),
              Expanded(
                child: ListView(
                  controller: controller,
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  children: [
                    Icon(Icons.health_and_safety, size: 60, color: color),
                    const SizedBox(height: 16),
                    Text(
                      title,
                      textAlign: TextAlign.center,
                      style: AppTheme.darkTheme.textTheme.displayMedium,
                    ),
                    const SizedBox(height: 32),
                    Text(
                      "ÇÖZÜM ÖNERİLERİ",
                      style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(
                          letterSpacing: 2, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 16),
                    ...recommendations.asMap().entries.map((entry) {
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            CircleAvatar(
                              radius: 12,
                              backgroundColor: color.withOpacity(0.2),
                              child: Text(
                                "${entry.key + 1}",
                                style: TextStyle(
                                    color: color,
                                    fontSize: 12,
                                    fontWeight: FontWeight.bold),
                              ),
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: Text(
                                entry.value,
                                style:
                                    const TextStyle(fontSize: 16, height: 1.4),
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                    const SizedBox(height: 32),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppTheme.critical.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                            color: AppTheme.critical.withOpacity(0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.info_outline,
                              color: AppTheme.critical),
                          const SizedBox(width: 12),
                          const Expanded(
                            child: Text(
                              "Bu öneriler bilgilendirme amaçlıdır. Rahatsızlık devam ederse doktora başvurun.",
                              style: TextStyle(
                                  fontSize: 12, color: Colors.white70),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    GradientButton(
                      text: "TAMAM",
                      onPressed: () => Navigator.pop(context),
                      gradient: LinearGradient(
                          colors: [color.withOpacity(0.8), color]),
                    ),
                    const SizedBox(height: 40),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
