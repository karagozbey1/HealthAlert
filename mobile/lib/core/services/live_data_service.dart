import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../models/live_status.dart';

/// Demo veya backend kaynaklı canlı sağlık verisini periyodik olarak yayınlar.
class LiveDataService {
  LiveDataService({this.demoMode = false});

  final bool demoMode;
  Timer? _timer;
  final _controller = StreamController<LiveStatus>.broadcast();

  Stream<LiveStatus> get stream => _controller.stream;

  /// Servisin periyodik veri akışını başlatır.
  void start({
    required String userId,
    required int intervalSeconds,
    Future<LiveStatus?> Function()? fetchFn,
  }) {
    _timer?.cancel();
    _timer = Timer.periodic(Duration(seconds: intervalSeconds), (_) async {
      try {
        LiveStatus? status;
        if (demoMode || fetchFn == null) {
          status = _generateDemoStatus(userId);
        } else {
          status = await fetchFn();
        }
        if (status != null && !_controller.isClosed) {
          _controller.add(status);
        }
      } catch (error) {
        debugPrint('[LiveDataService] Live data tick failed: $error');
      }
    });
    if (demoMode || fetchFn == null) {
      _controller.add(_generateDemoStatus(userId));
    }
  }

  /// Servisin çalışan periyodik veri akışını durdurur.
  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  void dispose() {
    stop();
    _controller.close();
  }

  static final _rng = Random();
  static int _tick = 0;

  static final _scenarios = [
    _DemoScenario('normal', 62, 72, 97, 99, 0.00, 0.07),
    _DemoScenario('elevated_hr', 100, 118, 96, 97, 0.08, 0.18),
    _DemoScenario('warning', 118, 130, 95, 96, 0.40, 0.65),
    _DemoScenario('normal', 65, 74, 97, 99, 0.00, 0.07),
    _DemoScenario('low_spo2', 72, 82, 88, 91, 0.08, 0.18),
    _DemoScenario('recovery', 76, 85, 95, 98, 0.02, 0.09),
    _DemoScenario('normal', 62, 72, 97, 99, 0.00, 0.07),
  ];

  static const _ticksPerScenario = 8;

  /// Demo modunda sıradaki senaryoya göre canlı durum örneği üretir.
  static LiveStatus _generateDemoStatus(String userId) {
    _tick++;
    final scenarioIdx = (_tick ~/ _ticksPerScenario) % _scenarios.length;
    final s = _scenarios[scenarioIdx];

    double rng(double lo, double hi) => lo + _rng.nextDouble() * (hi - lo);

    return LiveStatus(
      id: 'demo_$_tick',
      userId: userId,
      heartRate: double.parse(rng(s.hrMin, s.hrMax).toStringAsFixed(1)),
      spo2: double.parse(rng(s.spo2Min, s.spo2Max).toStringAsFixed(1)),
      motionScore:
          double.parse(rng(s.motionMin, s.motionMax).toStringAsFixed(2)),
      riskScore: s.riskScore,
      scenario: s.name,
      timestamp: DateTime.now(),
    );
  }
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class _DemoScenario {
  const _DemoScenario(
    this.name,
    this.hrMin,
    this.hrMax,
    this.spo2Min,
    this.spo2Max,
    this.motionMin,
    this.motionMax,
  );
  final String name;
  final double hrMin;
  final double hrMax;
  final double spo2Min;
  final double spo2Max;
  final double motionMin;
  final double motionMax;

  double get riskScore {
    switch (name) {
      case 'elevated_hr':
        return 0.40;
      case 'warning':
        return 0.65;
      case 'low_spo2':
        return 0.85;
      case 'critical':
        return 0.95;
      case 'recovery':
        return 0.15;
      default:
        return 0.08;
    }
  }
}
