import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Backend HTTP isteklerini token ve hata yönetimiyle yürüten istemcidir.
class ApiClient {
  ApiClient(
      {required this.baseUrl,
      this.onUnauthorized,
      this.timeout = const Duration(seconds: 15)});

  final String baseUrl;
  final Duration timeout;
  String? _token;

  final void Function()? onUnauthorized;

  /// Backend isteklerinde kullanılacak erişim tokenını saklar.
  void setToken(String token) => _token = token;

  /// Backend istemcisinde saklanan erişim tokenını temizler.
  void clearToken() => _token = null;
  bool get hasToken => _token != null;

  /// Backend isteği için JSON ve yetki başlıklarını hazırlar.
  Map<String, String> _headers({bool auth = true}) {
    final h = {'Content-Type': 'application/json'};
    if (auth && _token != null) {
      h['Authorization'] = 'Bearer $_token';
    }
    return h;
  }

  /// Backend path bilgisini tam HTTP URI değerine dönüştürür.
  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  /// Backend kaynağı için POST isteği gönderir.
  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    bool auth = true,
  }) async {
    final resp = await http
        .post(
          _uri(path),
          headers: _headers(auth: auth),
          body: jsonEncode(body),
        )
        .timeout(timeout);
    return _handle(resp);
  }

  /// Backend kaynağı için PUT isteği gönderir.
  Future<Map<String, dynamic>> put(
    String path,
    Map<String, dynamic> body,
  ) async {
    final resp = await http
        .put(
          _uri(path),
          headers: _headers(),
          body: jsonEncode(body),
        )
        .timeout(timeout);
    return _handle(resp);
  }

  /// Backend kaynağı için GET isteği gönderir.
  Future<dynamic> get(String path) async {
    final resp =
        await http.get(_uri(path), headers: _headers()).timeout(timeout);
    return _handleAny(resp);
  }

  /// Backend kaynağı için DELETE isteği gönderir.
  Future<void> delete(String path) async {
    final resp =
        await http.delete(_uri(path), headers: _headers()).timeout(timeout);
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, _extractError(resp));
    }
  }

  /// Backend HTTP yanıtını JSON verisine veya ApiException hatasına çevirir.
  Map<String, dynamic> _handle(http.Response resp) {
    final body = _handleAny(resp);
    if (body is Map<String, dynamic>) return body;
    throw ApiException(resp.statusCode, 'Unexpected response format');
  }

  /// Backend HTTP yanıtını boş, liste veya map JSON değerine dönüştürür.
  dynamic _handleAny(http.Response resp) {
    if (resp.statusCode == 401) {
      onUnauthorized?.call();
      throw ApiException(resp.statusCode, _extractError(resp));
    }
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, _extractError(resp));
    }
    if (resp.body.isEmpty) return {};
    return jsonDecode(resp.body);
  }

  /// Backend hata yanıtından kullanıcıya dönülecek mesajı çıkarır.
  String _extractError(http.Response resp) {
    try {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['detail']?.toString() ?? resp.reasonPhrase ?? 'Unknown error';
    } catch (error) {
      debugPrint('[ApiClient] Error response parse failed: $error');
      return resp.reasonPhrase ?? 'Unknown error';
    }
  }

  /// Backend health endpoint'ini çağırarak canlı mod erişimini kontrol eder.
  Future<bool> ping() async {
    try {
      final resp =
          await http.get(_uri('/health')).timeout(const Duration(seconds: 3));
      return resp.statusCode == 200;
    } catch (error) {
      debugPrint('[ApiClient] Health ping failed: $error');
      return false;
    }
  }

  /// Aktif kullanıcının backend profilini getirir.
  Future<Map<String, dynamic>> getMe() async {
    final data = await get('/users/me');
    if (data is Map<String, dynamic>) return data;
    throw const ApiException(200, 'Unexpected response format for /users/me');
  }

  /// Kullanıcının izleme yetkisi olan hastaları getirir.
  Future<List<Map<String, dynamic>>> getAccessiblePatients() async {
    final data = await get('/patients/accessible');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(
        200, 'Unexpected response format for /patients/accessible');
  }

  /// Seçili hastanın en güncel canlı durumunu getirir.
  Future<Map<String, dynamic>> getPatientLive(String patientId) async {
    final data = await get('/patients/$patientId/live');
    if (data is Map<String, dynamic>) return data;
    throw ApiException(
        200, 'Unexpected response format for /patients/$patientId/live');
  }

  /// Seçili hasta için özet kart verisini getirir.
  Future<Map<String, dynamic>> getPatientSummary(String patientId) async {
    final data = await get('/patients/$patientId/summary');
    if (data is Map<String, dynamic>) return data;
    throw ApiException(
        200, 'Unexpected response format for /patients/$patientId/summary');
  }

  /// Doktor rolündeki kullanıcının atanmış hastalarını getirir.
  Future<List<Map<String, dynamic>>> getDoctorPatients() async {
    final data = await get('/doctor/patients');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(
        200, 'Unexpected response format for /doctor/patients');
  }

  /// Yakın rolündeki kullanıcının izlediği hastaları getirir.
  Future<List<Map<String, dynamic>>> getRelativePatients() async {
    final data = await get('/relative/patients');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(
        200, 'Unexpected response format for /relative/patients');
  }
}

/// Backend HTTP hatasının durum kodu ve mesajını taşır.
class ApiException implements Exception {
  const ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  /// Hata bilgisini loglarda okunacak kısa metin formuna çevirir.
  @override
  String toString() => 'ApiException($statusCode): $message';

  bool get isUnauthorized => statusCode == 401;
  bool get isNotFound => statusCode == 404;
  bool get isForbidden => statusCode == 403;
}
