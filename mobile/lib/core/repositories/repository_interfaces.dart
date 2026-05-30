import '../models/alert_event.dart';
import '../models/anomaly_event.dart';
import '../models/app_settings.dart';
import '../models/device_state.dart';
import '../models/emergency_contact.dart';
import '../models/history_item.dart';
import '../models/notification_item.dart';
import '../models/user_profile.dart';

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class SessionRepository {
  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<bool> isLoggedIn();

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<void> saveSession(String userId);

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<void> clearSession();

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<String?> getSessionUserId();
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class UserRepository {
  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<UserProfile> getProfile(String userId);

  /// Kullanıcı profilini backend veya yerel repository üzerinden günceller.
  Future<UserProfile> updateProfile(UserProfile profile);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class AlertRepository {
  Future<List<AlertEvent>> getAlerts();

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  Future<AlertEvent?> getActiveAlert();

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  Future<void> upsertAlert(AlertEvent event);

  /// Alarm akışındaki ilgili işlemi mevcut durumla uyumlu şekilde yürütür.
  Future<void> closeAlert(String alertId);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class AnomalyRepository {
  Future<List<AnomalyEvent>> getAnomalies();

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<void> addAnomaly(AnomalyEvent event);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class HistoryRepository {
  Future<List<HistoryItem>> getHistory();

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<void> addHistory(HistoryItem item);

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<void> clearHistory();
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class SettingsRepository {
  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<AppSettings> getSettings();

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<AppSettings> saveSettings(AppSettings settings);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class DeviceRepository {
  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<DeviceState> getState();

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<DeviceState> saveState(DeviceState state);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class ContactRepository {
  Future<List<EmergencyContact>> getContacts();
  Future<List<EmergencyContact>> saveContacts(List<EmergencyContact> contacts);
}

/// Uygulama verisinin ilgili kaynakla okunup yazılmasını tanımlar.
abstract class NotificationRepository {
  Future<List<NotificationItem>> getNotifications();

  /// Bildirim listesini veya okundu bilgisini günceller.
  Future<void> addNotification(NotificationItem item);

  /// Repository katmanında ilgili verinin okuma veya yazma sözleşmesini tanımlar.
  Future<void> markAllRead();
}
