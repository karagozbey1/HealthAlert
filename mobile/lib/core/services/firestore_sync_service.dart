import 'dart:async';
import 'dart:collection';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import 'ble_device_service.dart';
import '../models/live_status.dart';

bool _firestoreAvailable = false;
FirebaseFirestore? _firestore;

Future<bool> initFirestoreSync({
  required String projectId,
}) async {
  if (projectId.isEmpty) {
    debugPrint('[FirestoreSync] No project ID configured – Firestore disabled');
    return false;
  }

  try {
    final instance = FirebaseFirestore.instance;
    await instance.collection('healthcheck').doc('ping').get().timeout(
      const Duration(seconds: 5),
      onTimeout: () => throw TimeoutException('Firestore ping timeout'),
    );
    _firestore = instance;
    _firestoreAvailable = true;
    debugPrint('[FirestoreSync] Firestore connected (project: $projectId)');
    return true;
  } catch (e) {
    debugPrint('[FirestoreSync] Firestore init failed: $e – sync disabled');
    _firestoreAvailable = false;
    _firestore = null;
    return false;
  }
}

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

  void start() {
    if (!_firestoreAvailable) {
      debugPrint('[FirestoreSync] Firestore not available – sync disabled');
      debugPrint('[FirestoreSync] Data will be sent to backend via HTTP instead');
      return;
    }

    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(
      Duration(seconds: flushIntervalSeconds),
      (_) => flush(),
    );

    debugPrint('[FirestoreSync] Sync started (batch=$batchSize, interval=${flushIntervalSeconds}s)');
  }

  void stop() {
    _flushTimer?.cancel();
    _flushTimer = null;
  }

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

  Future<void> syncLiveStatus(LiveStatus status) async {
    if (!_firestoreAvailable || _firestore == null) return;

    try {
      await _writeToFirestore('live_status', status.userId, {
        'id': status.id,
        'user_id': status.userId,
        'heart_rate': status.heartRate,
        'spo2': status.spo2,
        'motion_score': status.motionScore,
        'risk_score': status.riskScore,
        'scenario': status.scenario,
        'timestamp': status.timestamp.toIso8601String(),
      });
    } catch (e) {
      debugPrint('[FirestoreSync] Live status sync failed: $e');
      _lastError = e.toString();
      notifyListeners();
    }
  }

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

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    stop();
    super.dispose();
  }

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

Future<void> writeSensorDataToFirestore({
  required String userId,
  required Map<String, dynamic> packetData,
}) async {
  if (!_firestoreAvailable || _firestore == null) return;

  try {
    final docId =
        '${packetData['device_id']}_${packetData['packet_seq']}';
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
