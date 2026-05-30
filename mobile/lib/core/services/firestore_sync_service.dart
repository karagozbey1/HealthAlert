import 'dart:async';
import 'dart:collection';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import 'ble_device_service.dart';
import '../models/live_status.dart';

bool _firestoreAvailable = false;
FirebaseFirestore? _firestore;

const double _criticalRiskThreshold = 0.7;
const double _warningRiskThreshold = 0.5;
const double _watchRiskThreshold = 0.3;
const double _stillMovementThreshold = 0.2;
const double _lightMovementThreshold = 0.5;
const int _stablePpgMeasurementState = 3;
const int _staleStatusSeconds = 60;

/// Firestore istemcisini proje ayarına göre başlatıp kullanılabilirlik bilgisini günceller.
Future<bool> initFirestoreSync({
  required String projectId,
}) async {
  if (projectId.isEmpty) {
    debugPrint('[FirestoreSync] No project ID configured – Firestore disabled');
    return false;
  }

  try {
    _firestore = FirebaseFirestore.instance;
    _firestoreAvailable = true;
    debugPrint('[FirestoreSync] Firestore ready (project: $projectId)');
    return true;
  } catch (e) {
    debugPrint('[FirestoreSync] Firestore init failed: $e – sync disabled');
    _firestoreAvailable = false;
    _firestore = null;
    return false;
  }
}

/// BLE ve canlı durum verilerini Firestore belgeleriyle senkronize eder.
class FirestoreSyncService extends ChangeNotifier {
  FirestoreSyncService({
    required this.userId,
    this.batchSize = 10,
    this.flushIntervalSeconds = 5,
  });

  final String userId;
  final int batchSize;
  final int flushIntervalSeconds;

  final Queue<Map<String, dynamic>> _buffer = Queue();
  Timer? _flushTimer;
  bool _syncing = false;
  int _totalSynced = 0;
  int _totalFailed = 0;
  DateTime? _lastSyncTime;
  String? _lastError;

  bool get isAvailable => _firestoreAvailable;
  bool get isSyncing => _syncing;
  int get totalSynced => _totalSynced;
  int get totalFailed => _totalFailed;
  int get pendingCount => _buffer.length;
  DateTime? get lastSyncTime => _lastSyncTime;
  String? get lastError => _lastError;

  /// Servisin periyodik veri akışını başlatır.
  void start() {
    if (!_firestoreAvailable) {
      debugPrint('[FirestoreSync] Firestore not available – sync disabled');
      debugPrint(
          '[FirestoreSync] Data will be sent to backend via HTTP instead');
      return;
    }

    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(
      Duration(seconds: flushIntervalSeconds),
      (_) => flush(),
    );

    debugPrint(
        '[FirestoreSync] Sync started (batch=$batchSize, interval=${flushIntervalSeconds}s)');
  }

  /// Servisin çalışan periyodik veri akışını durdurur.
  void stop() {
    _flushTimer?.cancel();
    _flushTimer = null;
  }

  /// BLE telemetri paketini Firestore yazım kuyruğuna ekler.
  void addPacket(BlePacket packet) {
    final data = {
      ...packet.toJson(),
      'user_id': userId,
      'synced_at': DateTime.now().toIso8601String(),
      'backend_processed': false,
      'transport': 'ble',
    };
    _buffer.add(data);

    if (_buffer.length >= batchSize) {
      flush();
    }
  }

  /// Hastanın canlı durumunu Firestore live_status belgesine yazar.
  Future<void> syncLiveStatus(LiveStatus status) async {
    if (!_firestoreAvailable || _firestore == null) return;

    try {
      await _writeToFirestore(
          'live_status',
          status.userId,
          _buildLiveStatusMap(
            patientId: status.userId,
            status: status,
          ));
    } catch (e) {
      debugPrint('[FirestoreSync] Live status sync failed: $e');
      _lastError = e.toString();
      notifyListeners();
    }
  }

  /// Hasta telefonundan gelen canlı ölçümü Firestore hasta belgesine kaydeder.
  Future<void> writeLiveStatusForPatient(
    String patientId,
    LiveStatus status, {
    String? patientName,
  }) async {
    if (!_firestoreAvailable || _firestore == null) return;
    try {
      await _writeToFirestore(
        'live_status',
        patientId,
        _buildLiveStatusMap(
          patientId: patientId,
          status: status,
          patientName: patientName,
        ),
      );
    } catch (e) {
      debugPrint('[FirestoreSync] writeLiveStatusForPatient failed: $e');
      _lastError = e.toString();
      notifyListeners();
    }
  }

  /// Returns a real-time stream for [live_status/{patientId}].
  /// Used by doctor/relative screens to receive updates without polling.
  Stream<DocumentSnapshot<Map<String, dynamic>>> getLiveStatusStream(
      String patientId) {
    if (!_firestoreAvailable || _firestore == null) {
      return const Stream.empty();
    }
    return _firestore!.collection('live_status').doc(patientId).snapshots();
  }

  /// Firestore live_status belgesini mobil canlı durum modeline dönüştürür.
  static LiveStatus liveStatusFromFirestoreMap(
      Map<String, dynamic> data, String patientId) {
    DateTime parseTs(dynamic v) {
      if (v == null) return DateTime.now();
      if (v is Timestamp) return v.toDate();
      if (v is String) {
        try {
          return DateTime.parse(v);
        } catch (error) {
          debugPrint('[FirestoreSync] Timestamp parse failed: $error');
        }
      }
      return DateTime.now();
    }

    return LiveStatus(
      id: data['id'] as String? ?? '',
      userId: data['patient_id'] as String? ??
          data['user_id'] as String? ??
          patientId,
      heartRate: (data['heart_rate'] as num?)?.toDouble() ?? 0,
      spo2: (data['spo2'] as num?)?.toDouble() ?? 0,
      motionScore: (data['movement_percent'] as num?)?.toDouble() ??
          (data['motion_score'] as num?)?.toDouble() ??
          0.1,
      riskScore: (data['risk_score'] as num?)?.toDouble() ?? 0.05,
      scenario: data['scenario'] as String? ?? 'normal',
      timestamp: parseTs(data['updated_at'] ?? data['timestamp']),
      signalQuality: (data['signal_quality'] as num?)?.toDouble(),
      fingerPresent: data['finger_detected'] as bool?,
      heartRateValid: data['hr_valid'] as bool?,
      spo2Valid: data['spo2_valid'] as bool?,
      source: data['source'] as String?,
    );
  }

  /// Alarm kaydını Firestore alerts koleksiyonuna yazar.
  Future<void> writeAlert(
      String alertId, Map<String, dynamic> alertData) async {
    if (!_firestoreAvailable || _firestore == null) return;
    try {
      await _writeToFirestore('alerts', alertId, {
        ...alertData,
        'created_at':
            alertData['created_at'] ?? DateTime.now().toIso8601String(),
      });
    } catch (e) {
      debugPrint('[FirestoreSync] writeAlert failed: $e');
    }
  }

  /// Returns a real-time stream of alerts for a patient.
  Stream<QuerySnapshot<Map<String, dynamic>>> getPatientAlertsStream(
      String patientId) {
    if (!_firestoreAvailable || _firestore == null) {
      return const Stream.empty();
    }
    return _firestore!
        .collection('alerts')
        .where('patient_id', isEqualTo: patientId)
        .orderBy('created_at', descending: true)
        .limit(50)
        .snapshots();
  }

  /// Hasta geçmiş kaydını Firestore alt koleksiyonuna yazar.
  Future<void> writeHistoryRecord(
      String patientId, String recordId, Map<String, dynamic> data) async {
    if (!_firestoreAvailable || _firestore == null) return;
    try {
      await _firestore!
          .collection('history')
          .doc(patientId)
          .collection('records')
          .doc(recordId)
          .set({
        ...data,
        'patient_id': patientId,
        'record_id': recordId,
        'timestamp': data['timestamp'] ?? DateTime.now().toIso8601String(),
      });
    } catch (e) {
      debugPrint('[FirestoreSync] writeHistoryRecord failed: $e');
    }
  }

  /// Canlı hasta durumunu Firestore live_status payload formatına dönüştürür.
  static Map<String, dynamic> _buildLiveStatusMap({
    required String patientId,
    required LiveStatus status,
    String? patientName,
  }) {
    final riskScore = status.finalRiskScore ?? status.riskScore;
    String riskLevel;
    if (riskScore >= _criticalRiskThreshold) {
      riskLevel = 'critical';
    } else if (riskScore >= _warningRiskThreshold) {
      riskLevel = 'warning';
    } else if (riskScore >= _watchRiskThreshold) {
      riskLevel = 'watch';
    } else {
      riskLevel = 'normal';
    }

    final now = DateTime.now();
    final ageSec = now.difference(status.timestamp).inSeconds;

    return {
      'id': status.id,
      'patient_id': patientId,
      if (patientName != null) 'patient_name': patientName,
      'heart_rate': status.heartRate,
      'hr_valid': status.heartRateValid ?? true,
      'spo2': status.spo2,
      'spo2_valid': status.spo2Valid ?? true,
      'movement_percent': status.motionScore,
      'movement_label': _movementLabelForScore(status.motionScore),
      'risk_score': riskScore,
      'risk_level': riskLevel,
      'source': status.source ?? 'ble',
      'signal_quality': status.signalQuality ?? 1.0,
      'finger_detected': status.fingerPresent ?? true,
      'measurement_state': _stablePpgMeasurementState,
      'motion_artifact': false,
      'scenario': status.scenario,
      'timestamp': status.timestamp.toIso8601String(),
      'updated_at': now.toIso8601String(),
      'last_seen_seconds': ageSec,
      'is_stale': ageSec > _staleStatusSeconds,
      'active_alert_count': 0,
    };
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  static String _movementLabelForScore(double motionScore) {
    if (motionScore < _stillMovementThreshold) {
      return 'Hareketsiz';
    }
    if (motionScore < _lightMovementThreshold) {
      return 'Az Hareketli';
    }
    return 'Hareketli';
  }

  /// Bekleyen telemetri paketlerini Firestore'a toplu olarak yazar.
  Future<void> flush() async {
    if (_buffer.isEmpty || _syncing) return;
    if (!_firestoreAvailable || _firestore == null) {
      _buffer.clear();
      return;
    }

    _syncing = true;
    notifyListeners();

    try {
      final batch = <Map<String, dynamic>>[];
      final count = _buffer.length.clamp(0, batchSize);
      for (int i = 0; i < count; i++) {
        if (_buffer.isNotEmpty) {
          batch.add(_buffer.removeFirst());
        }
      }

      for (final data in batch) {
        final docId = '${data['device_id']}_${data['packet_seq']}';
        await _writeToFirestore('telemetry_packets', docId, data);
      }

      _totalSynced += batch.length;
      _lastSyncTime = DateTime.now();
      _lastError = null;
    } catch (e) {
      _totalFailed += _buffer.length;
      _lastError = e.toString();
      debugPrint('[FirestoreSync] Batch flush failed: $e');
    } finally {
      _syncing = false;
      notifyListeners();
    }
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    stop();
    super.dispose();
  }

  /// Verilen koleksiyon ve belge kimliğiyle Firestore yazma işlemini yapar.
  Future<void> _writeToFirestore(
    String collection,
    String docId,
    Map<String, dynamic> data,
  ) async {
    if (_firestore == null) return;

    try {
      await _firestore!.collection(collection).doc(docId).set(data);
    } catch (e) {
      debugPrint('[FirestoreSync] Write to $collection/$docId failed: $e');
      rethrow;
    }
  }
}

/// Ham sensör paketini Firestore telemetry_packets koleksiyonuna yazar.
Future<void> writeSensorDataToFirestore({
  required String userId,
  required Map<String, dynamic> packetData,
}) async {
  if (!_firestoreAvailable || _firestore == null) return;

  try {
    final docId = '${packetData['device_id']}_${packetData['packet_seq']}';
    await _firestore!.collection('telemetry_packets').doc(docId).set({
      ...packetData,
      'user_id': userId,
      'synced_at': DateTime.now().toIso8601String(),
      'backend_processed': false,
      'transport': 'ble',
    });
  } catch (e) {
    debugPrint('[FirestoreSync] writeSensorDataToFirestore failed: $e');
  }
}
