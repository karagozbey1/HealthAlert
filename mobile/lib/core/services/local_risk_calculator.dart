/// Computes a simple local runtime risk score from live BLE measurements.
///
/// This is NOT a clinical decision tool and NOT personalized.
/// It is a best-effort presentation indicator when backend/model risk is
/// unavailable. Backend/model risk always takes priority when present.
///
/// Architecture rule: BLE parser does NOT call this. The
/// TransportOrchestrator calls this after parsing each packet.
class LocalRiskCalculator {
  LocalRiskCalculator._();

  /// Returns a 0.0–1.0 risk score from the given measurement inputs.
  ///
  /// Returns 0.0 when [fingerPresent] is false (no measurement context).
  static double calculate({
    required bool fingerPresent,
    required double bpm,
    required bool bpmValid,
    required double spo2,
    required bool spo2Valid,
    required double movementPercent, // 0–100
    required double signalQuality,   // 0.0–1.0
  }) {
    if (!fingerPresent) return 0.0;

    double risk = 0.0;

    // BPM contribution
    if (bpmValid && bpm > 0) {
      if (bpm < 50) {
        risk += 20;
      } else if (bpm >= 100 && bpm < 120) {
        risk += 10;
      } else if (bpm >= 120 && bpm < 140) {
        risk += 20;
      } else if (bpm >= 140) {
        risk += 30;
      }
      // 50–99 bpm → +0 (normal range)
    }

    // SpO2 contribution
    if (spo2Valid && spo2 > 0) {
      if (spo2 >= 95) {
        // +0 (normal)
      } else if (spo2 >= 92) {
        risk += 15;
      } else if (spo2 >= 88) {
        risk += 30;
      } else {
        risk += 45;
      }
    }

    // Movement contribution
    if (movementPercent >= 80) {
      risk += 20;
    } else if (movementPercent >= 50) {
      risk += 12;
    } else if (movementPercent >= 20) {
      risk += 5;
    }
    // < 20 → +0

    // Low signal quality slightly increases uncertainty/risk
    if (signalQuality < 0.4) risk += 5;

    return (risk / 100.0).clamp(0.0, 1.0);
  }

  /// Returns a Turkish display label for the given 0.0–1.0 risk score.
  static String riskLevel(double score) {
    final pct = score * 100;
    if (pct <= 20) return 'Düşük';
    if (pct <= 50) return 'Orta';
    if (pct <= 75) return 'Yüksek';
    return 'Kritik';
  }
}
