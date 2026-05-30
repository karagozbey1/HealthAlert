import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiClient {
  ApiClient({required this.baseUrl, this.onUnauthorized, this.timeout = const Duration(seconds: 15)});

  final String baseUrl;
  final Duration timeout;
  String? _token;

  final void Function()? onUnauthorized;

  void setToken(String token) => _token = token;
  void clearToken() => _token = null;
  bool get hasToken => _token != null;

  Map<String, String> _headers({bool auth = true}) {
    final h = {'Content-Type': 'application/json'};
    if (auth && _token != null) {
      h['Authorization'] = 'Bearer $_token';
    }
    return h;
  }

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    bool auth = true,
  }) async {
    final resp = await http.post(
      _uri(path),
      headers: _headers(auth: auth),
      body: jsonEncode(body),
    ).timeout(timeout);
    return _handle(resp);
  }

  Future<Map<String, dynamic>> put(
    String path,
    Map<String, dynamic> body,
  ) async {
    final resp = await http.put(
      _uri(path),
      headers: _headers(),
      body: jsonEncode(body),
    ).timeout(timeout);
    return _handle(resp);
  }

  Future<dynamic> get(String path) async {
    final resp = await http.get(_uri(path), headers: _headers()).timeout(timeout);
    return _handleAny(resp);
  }

  Future<void> delete(String path) async {
    final resp = await http.delete(_uri(path), headers: _headers()).timeout(timeout);
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, _extractError(resp));
    }
  }

  Map<String, dynamic> _handle(http.Response resp) {
    final body = _handleAny(resp);
    if (body is Map<String, dynamic>) return body;
    throw ApiException(resp.statusCode, 'Unexpected response format');
  }

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

  String _extractError(http.Response resp) {
    try {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['detail']?.toString() ?? resp.reasonPhrase ?? 'Unknown error';
    } catch (_) {
      return resp.reasonPhrase ?? 'Unknown error';
    }
  }

  Future<bool> ping() async {
    try {
      final resp = await http.get(_uri('/health')).timeout(const Duration(seconds: 3));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ── Convenience wrappers ──────────────────────────────────────────

  /// GET /users/me — returns the current user's profile.
  Future<Map<String, dynamic>> getMe() async {
    final data = await get('/users/me');
    if (data is Map<String, dynamic>) return data;
    throw const ApiException(200, 'Unexpected response format for /users/me');
  }

  /// GET /patients/accessible — patients the caller is authorised to monitor.
  Future<List<Map<String, dynamic>>> getAccessiblePatients() async {
    final data = await get('/patients/accessible');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(200, 'Unexpected response format for /patients/accessible');
  }

  /// GET /patients/{patientId}/live — latest live status for a patient.
  Future<Map<String, dynamic>> getPatientLive(String patientId) async {
    final data = await get('/patients/$patientId/live');
    if (data is Map<String, dynamic>) return data;
    throw ApiException(200, 'Unexpected response format for /patients/$patientId/live');
  }

  /// GET /patients/{patientId}/summary — compact summary card for a patient.
  Future<Map<String, dynamic>> getPatientSummary(String patientId) async {
    final data = await get('/patients/$patientId/summary');
    if (data is Map<String, dynamic>) return data;
    throw ApiException(200, 'Unexpected response format for /patients/$patientId/summary');
  }

  /// GET /doctor/patients — doctor's assigned patients (doctor role only).
  Future<List<Map<String, dynamic>>> getDoctorPatients() async {
    final data = await get('/doctor/patients');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(200, 'Unexpected response format for /doctor/patients');
  }

  /// GET /relative/patients — relative's monitored patients (relative role only).
  Future<List<Map<String, dynamic>>> getRelativePatients() async {
    final data = await get('/relative/patients');
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    throw const ApiException(200, 'Unexpected response format for /relative/patients');
  }
}

class ApiException implements Exception {
  const ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => 'ApiException($statusCode): $message';

  bool get isUnauthorized => statusCode == 401;
  bool get isNotFound => statusCode == 404;
  bool get isForbidden => statusCode == 403;
}
