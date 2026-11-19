import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';
import 'auth_helpers.dart';

class OtpPage extends StatefulWidget {
  const OtpPage({super.key, required this.email});

  final String email;

  @override
  State<OtpPage> createState() => _OtpPageState();
}

class _OtpPageState extends State<OtpPage> {
  final _code = TextEditingController();
  bool _busy = false;
  int _remaining = 60;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _startCountdown();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _code.dispose();
    super.dispose();
  }

  void _startCountdown() {
    _timer?.cancel();
    setState(() => _remaining = 60);
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_remaining <= 1) {
        timer.cancel();
        setState(() => _remaining = 0);
      } else {
        setState(() => _remaining--);
      }
    });
  }

  Future<void> _verify() async {
    if (_code.text.length != 6) {
      _show('Kode harus terdiri dari 6 angka.');
      return;
    }
    setState(() => _busy = true);
    try {
      final response = await context.read<AuthState>().api.post(
        '/api/auth/verifikasi',
        {'email': widget.email, 'kode': _code.text},
        auth: false,
      );
      await context.read<AuthState>().signInWithResponse(response);
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
    } on ApiException catch (error) {
      if (mounted) _show(error.pesan);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    if (_remaining > 0) return;
    try {
      await context.read<AuthState>().api.post('/api/auth/kirim-ulang', {
        'email': widget.email,
      }, auth: false);
      if (mounted) {
        _show('Kode baru telah dikirim.');
        _startCountdown();
      }
    } on ApiException catch (error) {
      if (mounted) _show(error.pesan);
    }
  }

  void _show(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verifikasi email')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Masukkan kode OTP 6 angka yang dikirim ke email Anda.'),
            const SizedBox(height: 20),
            TextField(
              controller: _code,
              maxLength: 6,
              keyboardType: TextInputType.number,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineMedium,
              decoration: const InputDecoration(labelText: 'Kode OTP'),
            ),
            const SizedBox(height: 12),
            BusyButton(busy: _busy, label: 'Verifikasi', onPressed: _verify),
            TextButton(
              onPressed: _remaining == 0 ? _resend : null,
              child: Text(
                _remaining == 0
                    ? 'Kirim ulang kode'
                    : 'Kirim ulang dalam $_remaining detik',
              ),
            ),
          ],
        ),
      ),
    );
  }
}
