import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key});

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  int _days = 1;
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _items = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await context.read<AuthState>().api.get(
        '/api/histori',
        query: {'hari': '$_days'},
      );
      final rows = (response['laporan'] as List? ?? const []);
      _items = rows
          .whereType<Map>()
          .map((row) => Map<String, dynamic>.from(row))
          .toList();
    } on ApiException catch (error) {
      _error = error.pesan;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: theme.colorScheme.primaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Row(
                children: [
                  Icon(Icons.history, color: theme.colorScheme.primary),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Riwayat pemantauan kebun',
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  DropdownButton<int>(
                    value: _days,
                    underline: const SizedBox.shrink(),
                    items: const [1, 2, 3, 7]
                        .map(
                          (day) => DropdownMenuItem(
                            value: day,
                            child: Text('$day hari'),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() => _days = value);
                      _load();
                    },
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(36),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_error != null)
            _emptyState(
              context,
              icon: Icons.cloud_off_outlined,
              message: _error!,
              action: TextButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Coba lagi'),
              ),
            )
          else if (_items.isEmpty)
            _emptyState(
              context,
              icon: Icons.sensors_off_outlined,
              message: 'Belum ada laporan dalam $_days hari terakhir.',
            )
          else ...[
            Text(
              '${_items.length} laporan • $_days hari terakhir',
              style: theme.textTheme.labelLarge,
            ),
            const SizedBox(height: 8),
            for (final item in _items) _reportCard(context, item),
          ],
        ],
      ),
    );
  }

  Widget _emptyState(
    BuildContext context, {
    required IconData icon,
    required String message,
    Widget? action,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          children: [
            Icon(icon, size: 44, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            ?action,
          ],
        ),
      ),
    );
  }

  Widget _reportCard(BuildContext context, Map<String, dynamic> item) {
    final theme = Theme.of(context);
    final type = item['jenis']?.toString() ?? '';
    final diagnosis = item['penyakit_daun']?.toString();
    final fruit = item['kematangan_buah']?.toString();
    final time = item['waktu_pencatatan']?.toString() ?? '';
    final date = DateTime.tryParse(time);
    final displayTime = date == null
        ? time
        : '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year} '
              '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  type == 'sensor' ? Icons.sensors : Icons.fact_check_outlined,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    type.isEmpty ? 'Laporan' : type[0].toUpperCase() + type.substring(1),
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                Text(displayTime, style: theme.textTheme.labelSmall),
              ],
            ),
            const Divider(height: 22),
            Wrap(
              spacing: 18,
              runSpacing: 10,
              children: [
                _reading('Suhu udara', item['suhu_udara'], '°C'),
                _reading('Suhu tanah', item['suhu_tanah'], '°C'),
                _reading('Kelembapan tanah', item['kelembaban_tanah'], '%'),
                if (diagnosis != null && diagnosis.isNotEmpty)
                  _reading('Kondisi daun', diagnosis, ''),
                if (fruit != null && fruit.isNotEmpty)
                  _reading('Kematangan buah', fruit, ''),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _reading(String label, dynamic value, String unit) {
    if (value == null) return const SizedBox.shrink();
    return SizedBox(
      width: 140,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelSmall),
          Text(
            '$value$unit',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
