import '../models/alert_event.dart';
import '../models/anomaly_event.dart';
import '../models/app_settings.dart';
import '../models/device_state.dart';
import '../models/emergency_contact.dart';
import '../models/history_item.dart';
import '../models/notification_item.dart';
import '../models/user_profile.dart';

abstract class SessionRepository {
  Future<bool> isLoggedIn();
  Future<void> saveSession(String userId);
  Future<void> clearSession();
  Future<String?> getSessionUserId();
}

abstract class UserRepository {
  Future<UserProfile> getProfile(String userId);
  Future<UserProfile> updateProfile(UserProfile profile);
}

abstract class AlertRepository {
  Future<List<AlertEvent>> getAlerts();
  Future<AlertEvent?> getActiveAlert();
  Future<void> upsertAlert(AlertEvent event);
  Future<void> closeAlert(String alertId);
}

abstract class AnomalyRepository {
  Future<List<AnomalyEvent>> getAnomalies();
  Future<void> addAnomaly(AnomalyEvent event);
}

abstract class HistoryRepository {
  Future<List<HistoryItem>> getHistory();
  Future<void> addHistory(HistoryItem item);
  Future<void> clearHistory();
}

abstract class SettingsRepository {
  Future<AppSettings> getSettings();
  Future<AppSettings> saveSettings(AppSettings settings);
}

abstract class DeviceRepository {
  Future<DeviceState> getState();
  Future<DeviceState> saveState(DeviceState state);
}

abstract class ContactRepository {
  Future<List<EmergencyContact>> getContacts();
  Future<List<EmergencyContact>> saveContacts(List<EmergencyContact> contacts);
}

abstract class NotificationRepository {
  Future<List<NotificationItem>> getNotifications();
  Future<void> addNotification(NotificationItem item);
  Future<void> markAllRead();
}
