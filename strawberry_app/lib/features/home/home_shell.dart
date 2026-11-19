import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../auth_state.dart';
import '../ai_chat/tanya_ai_page.dart';
import '../dashboard/dashboard_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final name = (auth.user?['nama'] ?? '').toString();
    return Scaffold(
      appBar: AppBar(
        title: Text(_index == 0 ? 'Dashboard' : 'Tanya AI'),
        actions: [
          PopupMenuButton<String>(
            icon: CircleAvatar(
              child: Text(name.isEmpty ? '?' : name[0].toUpperCase()),
            ),
            onSelected: (value) {
              if (value == 'logout') auth.logout();
            },
            itemBuilder: (_) => [
              PopupMenuItem<String>(
                enabled: false,
                child: Text(name.isEmpty ? 'Akun' : name),
              ),
              const PopupMenuItem<String>(
                value: 'logout',
                child: Text('Keluar'),
              ),
            ],
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: IndexedStack(
        index: _index,
        children: const [DashboardPage(), TanyaAiPage()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.smart_toy_outlined),
            selectedIcon: Icon(Icons.smart_toy),
            label: 'Tanya AI',
          ),
        ],
      ),
    );
  }
}
