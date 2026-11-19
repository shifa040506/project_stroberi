import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';

class MonitoringTab extends StatefulWidget {
  const MonitoringTab({super.key});

  @override
  State<MonitoringTab> createState() => _MonitoringTabState();
}

class _MonitoringTabState extends State<MonitoringTab> {
  String _temperature = '--';
  String _soil = '--';
  String _fan = 'OFF';
  String _pump = 'OFF';
  String _updated = '-';
  Uint8List? _image;
  String _diagnosis = '';
  String _advice = '';
  bool _loading = false;
  bool _connected = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _fetchSensor();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _fetchSensor());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetchSensor() async {
    try {
      final data = await context.read<AuthState>().api.get('/api/sensor');
      if (!mounted) return;
      setState(() {
        _temperature = '${data['suhu'] ?? '--'} °C';
        _soil = '${data['kelembapan_tanah'] ?? '--'} %';
        _fan = '${data['kipas'] ?? 'OFF'}';
        _pump = '${data['pompa'] ?? 'OFF'}';
        _updated = '${data['waktu'] ?? '-'}';
        _connected = true;
      });
    } on ApiException {
      if (mounted) setState(() => _connected = false);
    }
  }

  Future<void> _control(String device, String action) async {
    try {
      await context.read<AuthState>().api.post('/api/control', {
        'device': device,
        'action': action,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Perintah $action dikirim ke $device.')),
        );
        _fetchSensor();
      }
    } on ApiException catch (error) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.pesan)));
    }
  }

  Future<void> _capture() async {
    final picked = await ImagePicker().pickImage(
      source: ImageSource.camera,
      imageQuality: 80,
      maxWidth: 1024,
    );
    if (picked == null) return;
    setState(() {
      _loading = true;
      _diagnosis = 'Menganalisis gambar...';
      _advice = '';
    });
    try {
      final bytes = await picked.readAsBytes();
      final response = await context.read<AuthState>().api.upload(
        '/api/predict-disease',
        bytes,
      );
      final disease = (response['penyakit_daun'] ?? '').toString();
      if (!mounted) return;
      setState(() {
        _image = bytes;
        _diagnosis =
            '${disease.replaceAll('_', ' ').toUpperCase()} (${response['confidence'] ?? '-'}%)';
      });
      if (disease.isNotEmpty && disease != 'Tidak yakin') {
        final ai = await context.read<AuthState>().api.post('/api/ai/tanya', {
          'pesan':
              "Daun stroberi saya terdeteksi '$disease'. Beri analisis singkat dan 3 langkah penanganan.",
        }, timeout: const Duration(seconds: 45));
        if (mounted) setState(() => _advice = (ai['jawaban'] ?? '').toString());
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _diagnosis = 'Gagal menganalisis';
          _advice = error.pesan;
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _fetchSensor,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          _welcomeCard(),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _sensorCard(
                  'Suhu udara',
                  _temperature,
                  Icons.thermostat,
                  Colors.orange,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _sensorCard(
                  'Kelembapan tanah',
                  _soil,
                  Icons.water_drop,
                  Colors.blue,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _relayCard(
            'Kipas pendingin',
            _fan,
            'kipas',
            Icons.wind_power,
            Colors.teal,
          ),
          const SizedBox(height: 12),
          _relayCard(
            'Pompa siram',
            _pump,
            'pompa',
            Icons.shower,
            Colors.lightBlue,
          ),
          const SizedBox(height: 20),
          Text(
            'Diagnosis penyakit daun',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: _loading ? null : _capture,
            icon: const Icon(Icons.camera_alt),
            label: Text(_loading ? 'Menganalisis...' : 'Foto daun & analisis'),
          ),
          if (_image != null) ...[
            const SizedBox(height: 16),
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Image.memory(_image!, height: 220, fit: BoxFit.cover),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _diagnosis,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    if (_loading)
                      const Padding(
                        padding: EdgeInsets.only(top: 12),
                        child: LinearProgressIndicator(),
                      ),
                    if (_advice.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(_advice),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _welcomeCard() {
    final name = (context.read<AuthState>().user?['nama'] ?? 'Pengguna')
        .toString();
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Halo, $name',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 4),
                  Text('Diperbarui $_updated'),
                ],
              ),
            ),
            Icon(
              _connected ? Icons.wifi : Icons.wifi_off,
              color: _connected ? Colors.green : Colors.red,
            ),
            const SizedBox(width: 6),
            Text(_connected ? 'Terhubung' : 'Offline'),
          ],
        ),
      ),
    );
  }

  Widget _sensorCard(String title, String value, IconData icon, Color color) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 8),
            Text(title, style: Theme.of(context).textTheme.labelMedium),
            Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _relayCard(
    String title,
    String status,
    String device,
    IconData icon,
    Color color,
  ) {
    final isOn = status.startsWith('ON');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Icon(icon, color: isOn ? color : Colors.grey),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                Text(
                  status,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: isOn ? color : Colors.grey,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _control(device, 'PULSE_1S'),
                    child: const Text('1 Detik'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed: () => _control(device, 'ON'),
                    child: const Text('ON'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _control(device, 'OFF'),
                    child: const Text('OFF'),
                  ),
                ),
              ],
            ),
            TextButton(
              onPressed: () => _control('system', 'AUTO'),
              child: const Text('Kembali ke Auto'),
            ),
          ],
        ),
      ),
    );
  }
}
