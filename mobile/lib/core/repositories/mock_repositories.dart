import 'dart:convert';

import '../models/alert_event.dart';
import '../models/anomaly_event.dart';
import '../models/app_settings.dart';
import '../models/device_state.dart';
import '../models/emergency_contact.dart';
import '../models/enums.dart';
import '../models/history_item.dart';
import '../models/notification_item.dart';
import '../models/user_profile.dart';
import 'local_store.dart';
import 'repository_interfaces.dart';

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockSessionRepository implements SessionRepository {
  static const _keyUserId = 'session_user_id';

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<String?> getSessionUserId() async {
    return LocalStore.getString(_keyUserId);
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<bool> isLoggedIn() async => (await getSessionUserId()) != null;

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  @override
  Future<void> saveSession(String userId) async {
    await LocalStore.setString(_keyUserId, userId);
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<void> clearSession() async {
    await LocalStore.remove(_keyUserId);
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockUserRepository implements UserRepository {
  UserProfile _profile = const UserProfile(
    id: 'u1',
    fullName: 'Ali Yilmaz',
    email: 'ali.yilmaz@email.com',
    phone: '+90 555 123 45 67',
    birthDate: '1960-01-01',
    deviceId: 'WH-8291-X2',
  );

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<UserProfile> getProfile(String userId) async => _profile;

  /// Kullanıcı profilini backend veya yerel repository üzerinden günceller.
  @override
  Future<UserProfile> updateProfile(UserProfile profile) async {
    _profile = profile;
    return _profile;
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockAlertRepository implements AlertRepository {
  final List<AlertEvent> _items = [];

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  @override
  Future<AlertEvent?> getActiveAlert() async {
    for (final a in _items.reversed) {
      if (a.isActive) return a;
    }
    return null;
  }

  @override
  Future<List<AlertEvent>> getAlerts() async =>
      List.unmodifiable(_items.reversed);

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  @override
  Future<void> upsertAlert(AlertEvent event) async {
    final i = _items.indexWhere((e) => e.id == event.id);
    if (i >= 0) {
      _items[i] = event;
    } else {
      _items.add(event);
    }
  }

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  @override
  Future<void> closeAlert(String alertId) async {
    final i = _items.indexWhere((e) => e.id == alertId);
    if (i >= 0) {
      _items[i] = _items[i].copyWith(
          status: AlertLifecycleStatus.closed, countdownRemainingSec: 0);
    }
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockAnomalyRepository implements AnomalyRepository {
  final List<AnomalyEvent> _items;

  MockAnomalyRepository(this._items);

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<void> addAnomaly(AnomalyEvent event) async => _items.add(event);

  @override
  Future<List<AnomalyEvent>> getAnomalies() async =>
      List.unmodifiable(_items.reversed);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockHistoryRepository implements HistoryRepository {
  static const _key = 'history_items';

  List<HistoryItem> _items = [];

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  Future<void> init() async {
    final raw = await LocalStore.getString(_key);
    if (raw == null) return;
    final arr = jsonDecode(raw) as List<dynamic>;
    _items = arr
        .map((e) => HistoryItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList(growable: true);
  }

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<void> _persist() async {
    final data = jsonEncode(_items.map((e) => e.toJson()).toList());
    await LocalStore.setString(_key, data);
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<void> addHistory(HistoryItem item) async {
    _items.add(item);
    await _persist();
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<void> clearHistory() async {
    _items = [];
    await _persist();
  }

  @override
  Future<List<HistoryItem>> getHistory() async =>
      List.unmodifiable(_items.reversed);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockSettingsRepository implements SettingsRepository {
  static const _key = 'app_settings';

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<AppSettings> getSettings() async {
    final raw = await LocalStore.getString(_key);
    if (raw == null) return AppSettings.defaults;
    return AppSettings.fromJson(
        Map<String, dynamic>.from(jsonDecode(raw) as Map));
  }

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  @override
  Future<AppSettings> saveSettings(AppSettings settings) async {
    await LocalStore.setString(_key, jsonEncode(settings.toJson()));
    return settings;
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockDeviceRepository implements DeviceRepository {
  DeviceState _state = DeviceState(
    batteryPercent: 92,
    isConnected: true,
    mode: BatteryMode.balanced,
    lastSync: DateTime.now(),
  );

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<DeviceState> getState() async => _state;

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  @override
  Future<DeviceState> saveState(DeviceState state) async {
    _state = state;
    return _state;
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockContactRepository implements ContactRepository {
  List<EmergencyContact> _items = const [
    EmergencyContact(
        id: 'c1',
        name: 'Ahmet Yilmaz',
        relation: 'Ogul',
        phone: '05551234567',
        isPrimary: true),
    EmergencyContact(
        id: 'c2',
        name: 'Ayse Demir',
        relation: 'Es',
        phone: '05559876543',
        isPrimary: false),
  ];

  @override
  Future<List<EmergencyContact>> getContacts() async =>
      List.unmodifiable(_items);

  @override
  Future<List<EmergencyContact>> saveContacts(
      List<EmergencyContact> contacts) async {
    _items = List.of(contacts);
    return List.unmodifiable(_items);
  }
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
class MockNotificationRepository implements NotificationRepository {
  final List<NotificationItem> _items = [];

  /// Bildirim listesini veya okundu bilgisini günceller.
  @override
  Future<void> addNotification(NotificationItem item) async => _items.add(item);

  @override
  Future<List<NotificationItem>> getNotifications() async =>
      List.unmodifiable(_items.reversed);

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  @override
  Future<void> markAllRead() async {
    for (var i = 0; i < _items.length; i++) {
      _items[i] = _items[i].copyWith(read: true);
    }
  }
}
