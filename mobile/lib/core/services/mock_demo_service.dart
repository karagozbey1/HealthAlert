import '../models/anomaly_event.dart';
import '../models/enums.dart';

class MockDemoService {
  List<AnomalyEvent> initialAnomalies() {
    final now = DateTime.now();
    return [
      AnomalyEvent(
        id: 'a1',
        metric: 'SpO2',
        value: 89,
        unit: '%',
        severity: AlertSeverity.critical,
        detectedAt: now.subtract(const Duration(minutes: 12)),
        summary: 'Düşük oksijen doygunluğu tespit edildi.',
      ),
      AnomalyEvent(
        id: 'a2',
        metric: 'Nabız',
        value: 118,
        unit: 'bpm',
        severity: AlertSeverity.warning,
        detectedAt: now.subtract(const Duration(minutes: 36)),
        summary: 'Nabız uyarı eşiğinin üzerinde.',
      ),
      AnomalyEvent(
        id: 'a3',
        metric: 'Düşme Riski',
        value: 0.62,
        unit: 'puan',
        severity: AlertSeverity.watch,
        detectedAt: now.subtract(const Duration(hours: 3)),
        summary: 'Artan denge bozukluğu deseni.',
      ),
    ];
  }
}
