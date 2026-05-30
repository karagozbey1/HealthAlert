import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../widgets/animated_chart_placeholder.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class MonitoringScreen extends StatelessWidget {
  const MonitoringScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final live = app.latestLiveStatus;
    final isLive = app.isBackendMode;

    return Scaffold(
      appBar: AppBar(title: const Text('Canlı İzleme')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Expanded(
              child: GlassCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Hareket Sensörü',
                            style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.white)),
                        Icon(Icons.sensors,
                            color: live != null
                                ? const Color(0xFF00E5FF)
                                : Colors.white30),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (live != null) ...[
                      _metricRow(
                          'Hareket Skoru',
                          '%${(live.motionScore * 100).toStringAsFixed(0)}',
                          live.motionScore > 0.75
                              ? AppTheme.warning
                              : const Color(0xFF00E5FF)),
                      const SizedBox(height: 8),
                      _metricRow('Senaryo', live.scenarioLabel,
                          live.isAlert ? AppTheme.warning : AppTheme.success),
                    ] else ...[
                      Expanded(
                        child: Center(
                          child: Text(
                            isLive
                                ? 'Henüz canlı veri alınmadı.\nCihaz bağlantısı bekleniyor.'
                                : 'Demo modda sensör verisi gösterilemiyor.',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Colors.white30, fontSize: 13),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Expanded(
              child: GlassCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Vital Değerler',
                            style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.white)),
                        Icon(Icons.monitor_heart,
                            color: live != null
                                ? Colors.greenAccent
                                : Colors.white30),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (live != null) ...[
                      _metricRow(
                          'Nabız',
                          '${live.heartRate.toStringAsFixed(0)} bpm',
                          (live.heartRate > 100 || live.heartRate < 50)
                              ? AppTheme.critical
                              : Colors.greenAccent),
                      const SizedBox(height: 8),
                      _metricRow(
                          'SpO2',
                          '%${live.spo2.toStringAsFixed(1)}',
                          live.spo2 < 94
                              ? AppTheme.critical
                              : Colors.greenAccent),
                      const SizedBox(height: 8),
                      _metricRow(
                          'Risk Skoru',
                          '%${(live.riskScore * 100).toStringAsFixed(0)}',
                          live.riskScore > 0.6
                              ? AppTheme.warning
                              : AppTheme.success),
                      const Spacer(),
                      Text(
                        'Son güncelleme: ${_timeStr(live.timestamp)}',
                        style: const TextStyle(
                            color: Colors.white30, fontSize: 10),
                      ),
                    ] else ...[
                      Expanded(
                        child: Center(
                          child: Text(
                            isLive
                                ? 'Henüz canlı veri alınmadı.\nCihaz bağlantısı bekleniyor.'
                                : 'Demo modda vital verisi gösterilemiyor.',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Colors.white30, fontSize: 13),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _metricRow(String label, String value, Color color) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label,
            style: const TextStyle(color: Colors.white54, fontSize: 13)),
        Text(value,
            style: TextStyle(
                color: color, fontSize: 16, fontWeight: FontWeight.bold)),
      ],
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  String _timeStr(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    final s = dt.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }
}
