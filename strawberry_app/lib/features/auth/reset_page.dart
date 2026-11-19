import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';
import 'auth_helpers.dart';

class ResetPage extends StatefulWidget {
  const ResetPage({super.key, required this.phone});

  final String phone;

  @override
  State<ResetPage> createState() => _ResetPageState();
}

class _ResetPageState extends State<ResetPage> {
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _code.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final passwordError = validatePassword(_password.text);
    if (_code.text.length != 6 ||
        passwordError != null ||
        _password.text != _confirm.text) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            passwordError ?? 'Kode dan password harus diisi dengan benar.',
          ),
        ),
      );
      return;
    }
    setState(() => _busy = true);
    try {
      await context.read<AuthState>().api.post('/api/auth/reset', {
        'phone': widget.phone,
        'kode': _code.text,
        'password_baru': _password.text,
      }, auth: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Password berhasil diubah.')),
      );
      Navigator.of(context).popUntil((route) => route.isFirst);
    } on ApiException catch (error) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.pesan)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reset password')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          TextField(
            controller: _code,
            maxLength: 6,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Kode OTP'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _password,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Password baru'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _confirm,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Ulangi password baru',
            ),
          ),
          const SizedBox(height: 24),
          BusyButton(busy: _busy, label: 'Simpan password', onPressed: _submit),
        ],
      ),
    );
  }
}
