import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'auth_state.dart';
import 'features/auth/login_page.dart';
import 'features/home/home_shell.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState()..start(),
      child: const StrawberryApp(),
    ),
  );
}

class StrawberryApp extends StatelessWidget {
  const StrawberryApp({super.key});

  static const _leafGreen = Color(0xFF2E7D32);
  static const _strawberryRed = Color(0xFFD7263D);

  ThemeData _theme(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
      seedColor: _leafGreen,
      brightness: brightness,
    ).copyWith(secondary: _strawberryRed);
    return ThemeData(useMaterial3: true, colorScheme: scheme);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Strawberry Care',
      debugShowCheckedModeBanner: false,
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      home: const AuthGate(),
    );
  }
}

class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    switch (context.watch<AuthState>().status) {
      case AuthStatus.checking:
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      case AuthStatus.signedOut:
        return const LoginPage();
      case AuthStatus.signedIn:
        return const HomeShell();
    }
  }
}
