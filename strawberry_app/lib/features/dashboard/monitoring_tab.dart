import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:image_cropper/image_cropper.dart'; // ROI: crop manual
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
  Uint8List? _leafImage;
  Uint8List? _fruitImage;
  String _leafDiagnosis = '';
  String _fruitDiagnosis = '';
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
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.pesan)));
      }
    }
  }

  // Crop manual khusus area daun sebelum pemeriksaan penyakit.
  Future<Uint8List?> _cropRoi(String path) async {
    final layar = MediaQuery.sizeOf(context);
    final cropWidth = math
        .min(layar.width - 24, 520.0)
        .clamp(280.0, 520.0)
        .round();
    final cropHeight = math
        .min(layar.height - 24, 520.0)
        .clamp(360.0, 520.0)
        .round();

    final cropped = await ImageCropper().cropImage(
      sourcePath: path,
      aspectRatio: const CropAspectRatio(ratioX: 1, ratioY: 1),
      maxWidth: 640, // cukup untuk model 224x224; unggahan lebih cepat
      maxHeight: 640,
      compressFormat: ImageCompressFormat.jpg,
      compressQuality: 85,
      uiSettings: [
        AndroidUiSettings(
          toolbarTitle: 'Pilih area gejala penyakit',
          lockAspectRatio: true,
          hideBottomControls: true,
          initAspectRatio: CropAspectRatioPreset.square,
        ),
        IOSUiSettings(
          title: 'Pilih area gejala penyakit',
          aspectRatioLockEnabled: true,
          resetAspectRatioEnabled: false,
        ),
        WebUiSettings(
          context: context,
          presentStyle: WebPresentStyle.dialog,
          size: CropperSize(width: cropWidth, height: cropHeight),
          viewwMode: WebViewMode.mode_3,
          dragMode: WebDragMode.move,
          modal: true,
          movable: true,
          scalable: true,
          zoomable: true,
          zoomOnTouch: true,
          zoomOnWheel: true,
          cropBoxMovable: true,
          cropBoxResizable: true,
          minContainerWidth: 280,
          minContainerHeight: 280,
          minCropBoxWidth: 120,
          minCropBoxHeight: 120,
          barrierColor: Colors.black54,
        ),
      ],
    );
    if (cropped == null) return null;
    return await cropped.readAsBytes();
  }

  Future<void> _capture(ImageSource sumber, {required bool fruit}) async {
    if (!mounted) return;
    final picked = await ImagePicker().pickImage(
      source: sumber,
      imageQuality: 90, // ROI: resolusi tinggi dulu agar hasil crop tetap tajam
      maxWidth: 2048,
      preferredCameraDevice: CameraDevice.rear,
    );
    if (picked == null) return;
    if (!mounted) return;
    debugPrint(
      fruit
          ? 'Foto buah dipilih untuk auto-crop backend: path=${picked.path}'
          : 'Foto daun diambil, membuka crop... path=${picked.path}',
    );

    final Uint8List? hasilFoto;
    try {
      hasilFoto = fruit
          ? await picked.readAsBytes()
          : await _cropRoi(picked.path);
    } catch (e) {
      debugPrint('Gagal menyiapkan foto untuk analisis: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              fruit
                  ? 'Foto tidak dapat dibaca: $e'
                  : 'Crop tidak tersedia di platform ini: $e',
            ),
          ),
        );
      }
      return;
    }
    if (hasilFoto == null) return;
    if (!mounted) return;
    final bytes = hasilFoto;

    setState(() {
      _loading = true;
      if (fruit) {
        _fruitDiagnosis = 'Menganalisis gambar...';
      } else {
        _leafDiagnosis = 'Menganalisis gambar...';
        _advice = '';
      }
    });
    try {
      final response = await context.read<AuthState>().api.upload(
        fruit ? '/api/predict-fruit' : '/api/predict-disease',
        bytes,
      );
      final result = (response[fruit ? 'kondisi_buah' : 'penyakit_daun'] ?? '')
          .toString();
      if (!mounted) return;
      setState(() {
        if (fruit) {
          _fruitImage = bytes;
          _fruitDiagnosis =
              '${result.replaceAll('_', ' ').toUpperCase()} (${response['confidence'] ?? '-'}%)';
        } else {
          _leafImage = bytes;
          _leafDiagnosis =
              '${result.replaceAll('_', ' ').toUpperCase()} (${response['confidence'] ?? '-'}%)';
        }
      });
      if (!fruit && result.isNotEmpty && result != 'Tidak yakin') {
        try {
          final ai = await context.read<AuthState>().api.post('/api/ai/tanya', {
            'pesan':
                "Daun stroberi saya terdeteksi '$result'. Beri analisis singkat dan 3 langkah penanganan.",
          }, timeout: const Duration(seconds: 45));
          if (mounted) {
            setState(() => _advice = (ai['jawaban'] ?? '').toString());
          }
        } on ApiException catch (error) {
          if (mounted) {
            setState(() => _advice = 'Saran AI tidak tersedia: ${error.pesan}');
          }
        }
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          if (fruit) {
            _fruitDiagnosis = 'Gagal menganalisis: ${error.pesan}';
          } else {
            _leafDiagnosis = 'Gagal menganalisis';
            _advice = error.pesan;
          }
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
            'Pemeriksaan tanaman',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _inspectionCard(
                  title: 'Penyakit daun',
                  icon: Icons.eco_outlined,
                  fruit: false,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _inspectionCard(
                  title: 'Kondisi buah',
                  icon: Icons.spa_outlined,
                  fruit: true,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.crop, size: 20),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Pemeriksaan daun menggunakan crop manual pada area gejala. '
                      'Foto buah dikirim utuh agar sistem melakukan auto-crop ROI (Region of Interest).',
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          _conclusionCard(),
          if (_advice.isNotEmpty) ...[
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Saran penanganan daun',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 6),
                    Text(_advice),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _inspectionCard({
    required String title,
    required IconData icon,
    required bool fruit,
  }) {
    final image = fruit ? _fruitImage : _leafImage;
    final diagnosis = fruit ? _fruitDiagnosis : _leafDiagnosis;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 4),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            if (image != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: AspectRatio(
                  aspectRatio: 1,
                  child: Image.memory(image, fit: BoxFit.cover),
                ),
              ),
            ],
            if (diagnosis.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(diagnosis, textAlign: TextAlign.center),
            ],
            if (_loading && diagnosis == 'Menganalisis gambar...')
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: LinearProgressIndicator(),
              ),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: _loading
                  ? null
                  : () => _capture(ImageSource.camera, fruit: fruit),
              icon: const Icon(Icons.camera_alt, size: 18),
              label: const Text('Kamera'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 6),
              ),
            ),
            OutlinedButton.icon(
              onPressed: _loading
                  ? null
                  : () => _capture(ImageSource.gallery, fruit: fruit),
              icon: const Icon(Icons.photo_library, size: 18),
              label: const Text('Galeri'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 6),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _conclusionCard() {
    final hasLeaf = _leafDiagnosis.isNotEmpty;
    final hasFruit = _fruitDiagnosis.isNotEmpty;
    final String conclusion;
    if (!hasLeaf && !hasFruit) {
      conclusion =
          'Lakukan pemeriksaan penyakit daun dan/atau kondisi buah. Kesimpulan akan tampil di sini.';
    } else if (hasLeaf && hasFruit) {
      conclusion =
          'Berdasarkan dua pemeriksaan, daun: $_leafDiagnosis; kondisi buah: $_fruitDiagnosis.';
    } else {
      final result = hasLeaf
          ? 'Daun: $_leafDiagnosis'
          : 'Buah: $_fruitDiagnosis';
      final missing = hasLeaf ? 'kondisi buah' : 'penyakit daun';
      conclusion = '$result. Periksa $missing untuk melengkapi kesimpulan.';
    }

    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Kesimpulan', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(conclusion),
          ],
        ),
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
