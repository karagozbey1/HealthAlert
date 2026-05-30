import 'package:shared_preferences/shared_preferences.dart';

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class LocalStore {
  LocalStore._();

  static SharedPreferences? _prefs;

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  static Future<SharedPreferences> _get() async {
    _prefs ??= await SharedPreferences.getInstance();
    return _prefs!;
  }

  /// Yerel depodan string ayar veya oturum değerini okur.
  static Future<String?> getString(String key) async {
    final p = await _get();
    return p.getString(key);
  }

  /// Yerel depoya string ayar veya oturum değerini yazar.
  static Future<void> setString(String key, String value) async {
    final p = await _get();
    await p.setString(key, value);
  }

  /// Yerel depodan verilen anahtara ait değeri siler.
  static Future<void> remove(String key) async {
    final p = await _get();
    await p.remove(key);
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  static Future<void> clear() async {
    final p = await _get();
    await p.clear();
  }

  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  static void resetForTest() => _prefs = null;
}
