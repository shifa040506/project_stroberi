import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'token_store.dart';

enum AuthStatus { checking, signedOut, signedIn }

class AuthState extends ChangeNotifier {
  AuthState() {
    api = ApiClient(onTidakSah: _sessionExpired);
  }

  late final ApiClient api;
  AuthStatus status = AuthStatus.checking;
  Map<String, dynamic>? user;

  Future<void> start() async {
    final token = await TokenStore.read();
    if (token == null || token.isEmpty) {
      _setStatus(AuthStatus.signedOut);
      return;
    }
    try {
      final response = await api.get('/api/auth/me');
      user = response['user'] as Map<String, dynamic>?;
      _setStatus(AuthStatus.signedIn);
    } on ApiException catch (error) {
      if (error.status == 401) {
        await TokenStore.clear();
        user = null;
        _setStatus(AuthStatus.signedOut);
      } else {
        _setStatus(AuthStatus.signedOut);
      }
    }
  }

  Future<void> login(String email, String password) async {
    final response = await api.post('/api/auth/login', {
      'email': email,
      'password': password,
    }, auth: false);
    await signInWithResponse(response);
  }

  Future<void> signInWithResponse(Map<String, dynamic> response) async {
    final token = response['token'];
    if (token is! String || token.isEmpty) {
      throw ApiException('Jawaban login tidak berisi token.');
    }
    await TokenStore.save(token);
    user = response['user'] as Map<String, dynamic>?;
    _setStatus(AuthStatus.signedIn);
  }

  Future<void> logout() async {
    await TokenStore.clear();
    user = null;
    _setStatus(AuthStatus.signedOut);
  }

  void _sessionExpired() {
    TokenStore.clear();
    user = null;
    _setStatus(AuthStatus.signedOut);
  }

  void _setStatus(AuthStatus next) {
    status = next;
    notifyListeners();
  }
}
