import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';

class ParameterTab extends StatefulWidget {
  const ParameterTab({super.key});

  @override
  State<ParameterTab> createState() => _ParameterTabState();
}

class _ParameterTabState extends State<ParameterTab> {
  static const _sensorInfo = <String, (String, String, IconData)>{
    'suhu_udara': ('Suhu udara', '°C', Icons.air),
    'suhu_tanah': ('Suhu tanah', '°C', Icons.thermostat),
    'kelembaban_tanah': ('Kelembapan tanah', '%', Icons.water_drop_outlined),
  };
  static const _fields = <String, String>{
    'batas_kritis_bawah': 'Kritis bawah',
    'batas_optimal_bawah': 'Optimal minimum',
    'batas_optimal_atas': 'Optimal maksimum',
    'batas_kritis_atas': 'Kritis atas',
  };

  final _controllers = <String, Map<String, TextEditingController>>{};
  final _formKeys = <String, GlobalKey<FormState>>{};
  bool _loading = true;
  bool _connected = false;
  String? _error;
  String? _saving;

  @override
  void initState() {
    super.initState();
    for (final sensor in _sensorInfo.keys) {
      _formKeys[sensor] = GlobalKey<FormState>();
      _controllers[sensor] = {
        for (final field in _fields.keys) field: TextEditingController(),
      };
    }
    _load();
  }

  @override
  void dispose() {
    for (final group in _controllers.values) {
      for (final controller in group.values) {
        controller.dispose();
      }
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await context.read<AuthState>().api.get(
        '/api/parameter',
      );
      if (!mounted) return;
      final rows = (response['parameter'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, dynamic>.from(row));
      _connected = true;
      for (final row in rows) {
        final sensor = row['sensor']?.toString();
        final fields = _controllers[sensor];
        if (fields == null) continue;
        for (final field in _fields.keys) {
          fields[field]!.text = row[field]?.toString() ?? '';
        }
      }
    } on ApiException catch (error) {
      _connected = false;
      _error = error.pesan;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save(String sensor) async {
    if (!_formKeys[sensor]!.currentState!.validate()) return;
    setState(() => _saving = sensor);
    try {
      await context.read<AuthState>().api.put(
        '/api/parameter/$sensor',
        _controllers[sensor]!.map((key, value) => MapEntry(key, value.text)),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Batas sensor berhasil disimpan.')),
      );
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.pesan)));
      }
    } finally {
      if (mounted) setState(() => _saving = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 60),
            Icon(Icons.tune, size: 56, color: theme.colorScheme.primary),
            const SizedBox(height: 16),
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            Center(
              child: OutlinedButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Coba lagi'),
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  CircleAvatar(
                    backgroundColor: _connected
                        ? theme.colorScheme.primaryContainer
                        : theme.colorScheme.errorContainer,
                    foregroundColor: _connected
                        ? theme.colorScheme.primary
                        : theme.colorScheme.error,
                    child: Icon(
                      _connected
                          ? Icons.storage_rounded
                          : Icons.cloud_off_rounded,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Ambang batas sensor',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'Atur nilai kritis dan rentang optimal sebagai acuan fuzzy logic.',
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Sinkronkan dari SQL',
                    onPressed: _loading ? null : _load,
                    icon: const Icon(Icons.sync_rounded),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.fromLTRB(6, 2, 6, 8),
            child: Row(
              children: [
                Icon(
                  _connected ? Icons.check_circle : Icons.error_outline,
                  size: 16,
                  color: _connected
                      ? theme.colorScheme.primary
                      : theme.colorScheme.error,
                ),
                const SizedBox(width: 7),
                Text(
                  _connected ? 'Terhubung' : 'Koneksi parameter belum tersedia',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: _connected
                        ? theme.colorScheme.primary
                        : theme.colorScheme.error,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          for (final entry in _sensorInfo.entries)
            _sensorCard(
              sensor: entry.key,
              title: entry.value.$1,
              unit: entry.value.$2,
              icon: entry.value.$3,
            ),
        ],
      ),
    );
  }

  Widget _sensorCard({
    required String sensor,
    required String title,
    required String unit,
    required IconData icon,
  }) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKeys[sensor],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    backgroundColor: theme.colorScheme.secondaryContainer,
                    child: Icon(
                      icon,
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(title, style: theme.textTheme.titleMedium),
                  ),
                  Text(unit, style: theme.textTheme.labelLarge),
                ],
              ),
              const SizedBox(height: 16),
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns = constraints.maxWidth > 440 ? 2 : 1;
                  final width =
                      (constraints.maxWidth - (columns - 1) * 10) / columns;
                  return Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      for (final field in _fields.entries)
                        SizedBox(
                          width: width,
                          child: TextFormField(
                            controller: _controllers[sensor]![field.key],
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true,
                              signed: true,
                            ),
                            decoration: InputDecoration(
                              labelText: field.value,
                              suffixText: unit,
                              border: const OutlineInputBorder(),
                              isDense: true,
                            ),
                            validator: (value) {
                              final number = double.tryParse(
                                value?.trim() ?? '',
                              );
                              if (number == null || !number.isFinite) {
                                return 'Masukkan angka yang valid';
                              }
                              return null;
                            },
                          ),
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _saving == null ? () => _save(sensor) : null,
                  icon: _saving == sensor
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: const Text('Simpan batas sensor'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
