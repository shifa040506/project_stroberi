import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'config.dart';
import 'token_store.dart';

class ApiException implements Exception {
  ApiException(this.pesan, {this.status, this.kode});

  final String pesan;
  final int? status;
  final String? kode;

  @override
  String toString() => pesan;
}

class ApiClient {
  ApiClient({this.onTidakSah});

  final void Function()? onTidakSah;

  Uri _uri(String path) => Uri.parse('${AppConfig.apiUrl}$path');

  Future<Map<String, String>> _headers({
    required bool auth,
    bool json = true,
  }) async {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (auth) {
      final token = await TokenStore.read();
      if (token != null && token.isNotEmpty) {
        headers['Authorization'] = 'Bearer $token';
      }
    }
    return headers;
  }

  Future<Map<String, dynamic>> get(
    String path, {
    bool auth = true,
    Duration timeout = const Duration(seconds: 10),
  }) {
    return _run(
      () async => http.get(_uri(path), headers: await _headers(auth: auth)),
      auth: auth,
      timeout: timeout,
    );
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    bool auth = true,
    Duration timeout = const Duration(seconds: 15),
  }) {
    return _run(
      () async => http.post(
        _uri(path),
        headers: await _headers(auth: auth),
        body: jsonEncode(body),
      ),
      auth: auth,
      timeout: timeout,
    );
  }

  Future<Map<String, dynamic>> upload(
    String path,
    Uint8List bytes, {
    String field = 'file',
    String filename = 'foto.jpg',
    Duration timeout = const Duration(seconds: 40),
  }) {
    return _run(
      () async {
        final request = http.MultipartRequest('POST', _uri(path));
        request.headers.addAll(await _headers(auth: true, json: false));
        request.files.add(
          http.MultipartFile.fromBytes(field, bytes, filename: filename),
        );
        return http.Response.fromStream(await request.send());
      },
      auth: true,
      timeout: timeout,
    );
  }

  Future<Map<String, dynamic>> _run(
    Future<http.Response> Function() request, {
    required bool auth,
    required Duration timeout,
  }) async {
    try {
      final response = await request().timeout(timeout);
      Map<String, dynamic> data = {};
      if (response.bodyBytes.isNotEmpty) {
        final decoded = jsonDecode(utf8.decode(response.bodyBytes));
        if (decoded is Map<String, dynamic>) data = decoded;
      }
      if (response.statusCode >= 200 && response.statusCode < 300) return data;
      if (response.statusCode == 401 && auth) onTidakSah?.call();
      throw ApiException(
        (data['error'] ??
                data['detail'] ??
                'Server menjawab error ${response.statusCode}')
            .toString(),
        status: response.statusCode,
        kode: data['kode_error']?.toString(),
      );
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException(
        'Server tidak menjawab. Cek koneksi dan alamat server.',
      );
    } on FormatException {
      throw ApiException('Jawaban server tidak dikenali.');
    } on http.ClientException {
      throw ApiException(
        'Tidak bisa terhubung ke server. Pastikan Flask menyala.',
      );
    }
  }
}
