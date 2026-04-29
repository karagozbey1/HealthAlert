enum UserRole {
  self,
  relative,
  doctor,
}

enum AlertSeverity {
  normal,
  watch,
  warning,
  critical,
}

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

enum HistoryItemType {
  alert,
  anomaly,
  status,
  notification,
}

enum NotificationChannel {
  inApp,
  local,
}

enum BatteryMode {
  performance,
  balanced,
  saver,
}

enum AppEnvironment {
  mock,
  firebase,
}
