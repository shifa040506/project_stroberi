import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

class ApiException implements Exception {
  final String pesan;
  ApiException(this.pesan);
  @override
  String toString() => pesan;
}

/// Alamat server dan (opsional) API key, disimpan di perangkat.
class Pengaturan {
  final String url;
  final String key;
  const Pengaturan(this.url, this.key);

  static Future<Pengaturan> muat() async {
    try {
      final sp = await SharedPreferences.getInstance();
      return Pengaturan(sp.getString('url') ?? '', sp.getString('key') ?? '');
    } catch (_) {
      return const Pengaturan('', '');
    }
  }

  Future<void> simpan() async {
    final sp = await SharedPreferences.getInstance();
    await sp.setString('url', url);
    await sp.setString('key', key);
  }

  /// "192.168.1.5:5000/" -> "http://192.168.1.5:5000"
  static String rapikan(String u) {
    u = u.trim();
    if (u.isEmpty) return '';
    if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'http://$u';
    while (u.endsWith('/')) {
      u = u.substring(0, u.length - 1);
    }
    return u;
  }
}

/// Klien untuk server Flask (app.py).
class ApiClient {
  final String baseUrl;
  final String apiKey; // Flask belum memakai API key; dikirim hanya kalau diisi
  ApiClient(this.baseUrl, this.apiKey);

  bool get siap => baseUrl.isNotEmpty;

  Map<String, String> get _headers =>
      apiKey.isEmpty ? <String, String>{} : {'X-API-Key': apiKey};

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  String _pesanGalat(int kode, String body) {
    String detail = '';
    try {
      final j = jsonDecode(body);
      if (j is Map)
        detail = (j['detail'] ?? j['error'] ?? '')
            .toString(); // Flask memakai 'error'
    } catch (_) {}
    switch (kode) {
      case 400:
        return detail.isNotEmpty ? detail : 'Foto tidak valid.';
      case 413:
        return 'Foto terlalu besar.';
      case 404:
        return detail.isNotEmpty ? detail : 'Alamat tidak ditemukan di server.';
      case 500:
        return 'Server Flask error: ${detail.isNotEmpty ? detail : 'lihat terminal Flask'}';
      default:
        return 'Server menjawab error $kode${detail.isNotEmpty ? ': $detail' : ''}';
    }
  }

  Future<T> _jalankan<T>(
    Future<http.Response> Function() req,
    T Function(dynamic) urai, {
    Duration timeout = const Duration(seconds: 20),
  }) async {
    if (!siap) {
      throw ApiException('Alamat server belum diisi. Buka tab Pengaturan.');
    }
    const gagalSambung =
        'Tidak bisa terhubung ke server. Cek alamat, Wi-Fi yang sama, Flask menyala, dan firewall port 5000.';
    try {
      final r = await req().timeout(timeout);
      final body = utf8.decode(r.bodyBytes);
      if (r.statusCode != 200)
        throw ApiException(_pesanGalat(r.statusCode, body));
      return urai(jsonDecode(body));
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException(
        'Server tidak menjawab (timeout). Cek alamat dan pastikan Flask menyala.',
      );
    } on SocketException {
      throw ApiException(gagalSambung);
    } on http.ClientException {
      throw ApiException(gagalSambung);
    } on FormatException {
      throw ApiException(
        'Jawaban server tidak dikenali. Pastikan alamatnya benar.',
      );
    } on TypeError {
      throw ApiException('Format jawaban server tidak sesuai.');
    }
  }

  /// Flask tidak punya /health; /api/sensor selalu menjawab kalau server hidup.
  Future<Map<String, dynamic>> health() => _jalankan(
    () => http.get(_uri('/api/sensor'), headers: _headers),
    (j) => Map<String, dynamic>.from(j as Map),
    timeout: const Duration(seconds: 8),
  );

  Future<Prediksi> predict(
    String pathFoto, {
    String perangkat = 'flutter-app',
  }) => _jalankan(
    () async {
      final m = http.MultipartRequest('POST', _uri('/api/predict-disease'));
      m.headers.addAll(_headers);
      m.files.add(await http.MultipartFile.fromPath('file', pathFoto));
      return http.Response.fromStream(await m.send());
    },
    (j) => Prediksi.fromFlask(Map<String, dynamic>.from(j as Map)),
    timeout: const Duration(seconds: 40),
  );

  /// Riwayat Flask disimpan di Firebase dan belum punya endpoint untuk aplikasi.
  Future<List<RiwayatItem>> riwayat({int limit = 50}) async {
    throw ApiException(
      'Riwayat belum tersedia di server Flask (data tersimpan di Firebase).',
    );
  }
}
