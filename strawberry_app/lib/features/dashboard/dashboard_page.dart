import 'package:flutter/material.dart';

import 'monitoring_tab.dart';
import 'parameter_tab.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(icon: Icon(Icons.monitor_heart_outlined), text: 'Monitoring'),
              Tab(icon: Icon(Icons.tune), text: 'Parameter'),
            ],
          ),
          Expanded(
            child: TabBarView(children: [MonitoringTab(), ParameterTab()]),
          ),
        ],
      ),
    );
  }
}
