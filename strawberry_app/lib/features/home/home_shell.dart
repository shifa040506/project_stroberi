import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../auth_state.dart';
import '../ai_chat/tanya_ai_page.dart';
import '../dashboard/dashboard_page.dart';
import '../history/history_page.dart';
import '../profile/profile_page.dart';

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
    const titles = ['Dashboard', 'Histori', 'Tanya AI', 'Profil Kebun'];
    return Scaffold(
      appBar: AppBar(
        leading: Padding(
          padding: const EdgeInsets.all(12),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              Icons.eco_rounded,
              color: Theme.of(context).colorScheme.primary,
              size: 21,
            ),
          ),
        ),
        title: Text(titles[_index]),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Menu akun',
            icon: CircleAvatar(
              radius: 19,
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              foregroundColor: Theme.of(context).colorScheme.primary,
              child: Text(
                name.isEmpty ? '?' : name[0].toUpperCase(),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
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
        children: const [
          DashboardPage(),
          HistoryPage(),
          TanyaAiPage(),
          ProfilePage(),
        ],
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
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: 'Histori',
          ),
          NavigationDestination(
            icon: Icon(Icons.smart_toy_outlined),
            selectedIcon: Icon(Icons.smart_toy),
            label: 'Tanya AI',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline_rounded),
            selectedIcon: Icon(Icons.person_rounded),
            label: 'Profil',
          ),
        ],
      ),
    );
  }
}
