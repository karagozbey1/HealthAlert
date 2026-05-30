/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum UserRole {
  self,
  relative,
  doctor,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum AlertSeverity {
  normal,
  watch,
  warning,
  critical,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum AlertLifecycleStatus {
  detected,
  raised,
  countdown,
  acknowledged,
  emergencyRequested,
  timedOut,
  postEventMonitoring,
  closed,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum HistoryItemType {
  alert,
  anomaly,
  status,
  notification,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum NotificationChannel {
  inApp,
  local,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum BatteryMode {
  performance,
  balanced,
  saver,
}

/// Mobil uygulamada kullanılan rol, alarm ve durum seçeneklerini tanımlar.
enum AppEnvironment {
  mock,
  firebase,
}
