import 'package:shared_preferences/shared_preferences.dart';

class LocalStore {
  LocalStore._();

  static SharedPreferences? _prefs;

  static Future<SharedPreferences> _get() async {
    _prefs ??= await SharedPreferences.getInstance();
    return _prefs!;
  }

  static Future<String?> getString(String key) async {
    final p = await _get();
    return p.getString(key);
  }

  static Future<void> setString(String key, String value) async {
    final p = await _get();
    await p.setString(key, value);
  }

  static Future<void> remove(String key) async {
    final p = await _get();
    await p.remove(key);
  }

  static Future<void> clear() async {
    final p = await _get();
    await p.clear();
  }

  static void resetForTest() => _prefs = null;
}
