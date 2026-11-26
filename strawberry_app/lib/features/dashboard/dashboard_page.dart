import 'package:flutter/material.dart';

import 'monitoring_tab.dart';
import 'parameter_tab.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          Material(
            color: colors.surface,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
              child: TabBar(
                dividerColor: Colors.transparent,
                indicatorSize: TabBarIndicatorSize.tab,
                indicator: BoxDecoration(
                  color: colors.primaryContainer,
                  borderRadius: const BorderRadius.all(Radius.circular(14)),
                ),
                labelColor: colors.primary,
                unselectedLabelColor: colors.onSurfaceVariant,
                labelStyle: const TextStyle(fontWeight: FontWeight.w700),
                tabs: const [
                  Tab(
                    icon: Icon(Icons.monitor_heart_outlined),
                    text: 'Monitoring',
                  ),
                  Tab(icon: Icon(Icons.tune_rounded), text: 'Parameter'),
                ],
              ),
            ),
          ),
          const Expanded(
            child: TabBarView(children: [MonitoringTab(), ParameterTab()]),
          ),
        ],
      ),
    );
  }
}
