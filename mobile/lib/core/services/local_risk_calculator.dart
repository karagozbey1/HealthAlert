/// BLE ölçümlerinden mobilde gösterilecek yerel risk skorunu hesaplar.
class LocalRiskCalculator {
  LocalRiskCalculator._();

  static const double _lowHeartRateBpm = 50;
  static const double _elevatedHeartRateBpm = 100;
  static const double _warningHeartRateBpm = 120;
  static const double _criticalHeartRateBpm = 140;
  static const double _normalSpo2Percent = 95;
  static const double _watchSpo2Percent = 92;
  static const double _criticalSpo2Percent = 88;
  static const double _highMovementPercent = 80;
  static const double _mediumMovementPercent = 50;
  static const double _lowMovementPercent = 20;
  static const double _lowSignalQuality = 0.4;
  static const double _scorePercentScale = 100;

  /// Canlı BLE ölçümlerinden yerel risk skoru ve senaryo etiketi hesaplar.
  static double calculate({
    required bool fingerPresent,
    required double bpm,
    required bool bpmValid,
    required double spo2,
    required bool spo2Valid,
    required double movementPercent, // 0–100
    required double signalQuality, // 0.0–1.0
  }) {
    if (!fingerPresent) return 0.0;

    double risk = 0.0;

    // BPM contribution
    if (bpmValid && bpm > 0) {
      if (bpm < _lowHeartRateBpm) {
        risk += 20;
      } else if (bpm >= _elevatedHeartRateBpm && bpm < _warningHeartRateBpm) {
        risk += 10;
      } else if (bpm >= _warningHeartRateBpm && bpm < _criticalHeartRateBpm) {
        risk += 20;
      } else if (bpm >= _criticalHeartRateBpm) {
        risk += 30;
      }
      // 50–99 bpm → +0 (normal range)
    }

    // SpO2 contribution
    if (spo2Valid && spo2 > 0) {
      if (spo2 >= _normalSpo2Percent) {
        // +0 (normal)
      } else if (spo2 >= _watchSpo2Percent) {
        risk += 15;
      } else if (spo2 >= _criticalSpo2Percent) {
        risk += 30;
      } else {
        risk += 45;
      }
    }

    // Movement contribution
    if (movementPercent >= _highMovementPercent) {
      risk += 20;
    } else if (movementPercent >= _mediumMovementPercent) {
      risk += 12;
    } else if (movementPercent >= _lowMovementPercent) {
      risk += 5;
    }
    // < 20 → +0

    // Low signal quality slightly increases uncertainty/risk
    if (signalQuality < _lowSignalQuality) risk += 5;

    return (risk / _scorePercentScale).clamp(0.0, 1.0);
  }

  /// Sayısal risk skorunu Türkçe risk seviyesi etiketine çevirir.
  static String riskLevel(double score) {
    final pct = score * _scorePercentScale;
    if (pct <= 20) return 'Düşük';
    if (pct <= 50) return 'Orta';
    if (pct <= 75) return 'Yüksek';
    return 'Kritik';
  }
}
