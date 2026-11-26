import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  static const _textFields = <String, String>{
    'alamat': 'Alamat',
    'desa_kelurahan': 'Desa / kelurahan',
    'kecamatan': 'Kecamatan',
    'kabupaten_kota': 'Kabupaten / kota',
    'provinsi': 'Provinsi',
    'kode_pos': 'Kode pos',
    'varietas': 'Varietas stroberi',
    'kode_perangkat': 'Kode perangkat',
    'nomor_kontak': 'Nomor kontak kebun',
  };
  static const _numberFields = <String, String>{
    'latitude': 'Latitude',
    'longitude': 'Longitude',
    'ketinggian_mdpl': 'Ketinggian (mdpl)',
    'luas_lahan_m2': 'Luas lahan (m²)',
    'jumlah_tanaman': 'Jumlah tanaman',
  };
  static const _mediaOptions = <String, String>{
    'tanah': 'Tanah',
    'cocopeat': 'Cocopeat',
    'hidroponik': 'Hidroponik',
    'lainnya': 'Lainnya',
  };
  static const _systemOptions = <String, String>{
    'greenhouse': 'Greenhouse',
    'lahan_terbuka': 'Lahan terbuka',
  };

  final _formKey = GlobalKey<FormState>();
  final _controllers = <String, TextEditingController>{};
  String? _media;
  String? _system;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controllers['nama_kebun'] = TextEditingController();
    for (final key in [
      ..._textFields.keys,
      ..._numberFields.keys,
      'catatan',
      'tanggal_mulai_tanam',
    ]) {
      _controllers[key] = TextEditingController();
    }
    _load();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
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
        '/api/profil-kebun',
      );
      if (!mounted) return;
      final profile = response['profil'];
      if (profile is Map) {
        final data = Map<String, dynamic>.from(profile);
        for (final entry in _controllers.entries) {
          entry.value.text = data[entry.key]?.toString() ?? '';
        }
        _media = data['jenis_media']?.toString();
        _system = data['sistem_tanam']?.toString();
      }
    } on ApiException catch (error) {
      _error = error.pesan;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final payload = <String, dynamic>{
      for (final entry in _controllers.entries)
        entry.key: entry.value.text.trim(),
      'jenis_media': _media,
      'sistem_tanam': _system,
    };
    try {
      await context.read<AuthState>().api.put('/api/profil-kebun', payload);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profil kebun berhasil disimpan.')),
      );
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.pesan)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Muat ulang'),
              ),
            ],
          ),
        ),
      );
    }
    return Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          _intro(),
          const SizedBox(height: 12),
          _section(
            title: 'Identitas kebun',
            icon: Icons.agriculture_outlined,
            children: [
              _input('nama_kebun', 'Nama kebun', required: true),
              _input('alamat', 'Alamat', lines: 2),
              _input('desa_kelurahan', 'Desa / kelurahan'),
              _input('kecamatan', 'Kecamatan'),
              _input('kabupaten_kota', 'Kabupaten / kota'),
              _input('provinsi', 'Provinsi'),
              _input('kode_pos', 'Kode pos'),
            ],
          ),
          _section(
            title: 'Detail budidaya',
            icon: Icons.spa_outlined,
            children: [
              _input('varietas', 'Varietas stroberi'),
              DropdownButtonFormField<String>(
                initialValue: _media,
                decoration: const InputDecoration(
                  labelText: 'Jenis media tanam',
                  border: OutlineInputBorder(),
                ),
                items: _mediaOptions.entries
                    .map(
                      (entry) => DropdownMenuItem(
                        value: entry.key,
                        child: Text(entry.value),
                      ),
                    )
                    .toList(),
                onChanged: (value) => setState(() => _media = value),
              ),
              DropdownButtonFormField<String>(
                initialValue: _system,
                decoration: const InputDecoration(
                  labelText: 'Sistem tanam',
                  border: OutlineInputBorder(),
                ),
                items: _systemOptions.entries
                    .map(
                      (entry) => DropdownMenuItem(
                        value: entry.key,
                        child: Text(entry.value),
                      ),
                    )
                    .toList(),
                onChanged: (value) => setState(() => _system = value),
              ),
              _input('tanggal_mulai_tanam', 'Tanggal mulai tanam (YYYY-MM-DD)'),
              _input('jumlah_tanaman', 'Jumlah tanaman', numeric: true),
              _input('luas_lahan_m2', 'Luas lahan (m²)', numeric: true),
            ],
          ),
          _section(
            title: 'Lokasi & perangkat',
            icon: Icons.location_on_outlined,
            children: [
              _input('latitude', 'Latitude', numeric: true),
              _input('longitude', 'Longitude', numeric: true),
              _input('ketinggian_mdpl', 'Ketinggian (mdpl)', numeric: true),
              _input('kode_perangkat', 'Kode perangkat'),
              _input('nomor_kontak', 'Nomor kontak kebun'),
              _input('catatan', 'Catatan tambahan', lines: 3),
            ],
          ),
          const SizedBox(height: 6),
          FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: _saving
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.save_outlined),
            label: const Text('Simpan profil kebun'),
          ),
        ],
      ),
    );
  }

  Widget _intro() {
    final name = context.watch<AuthState>().user?['nama']?.toString() ?? '';
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              radius: 25,
              child: Text(name.isEmpty ? 'K' : name[0].toUpperCase()),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Profil kebun',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    'Lengkapi informasi kebun agar data sensor dan laporan terhubung.',
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 9),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 14),
            ...[
              for (var index = 0; index < children.length; index++) ...[
                if (index > 0) const SizedBox(height: 12),
                children[index],
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _input(
    String key,
    String label, {
    bool required = false,
    bool numeric = false,
    int lines = 1,
  }) {
    final isInteger = key == 'jumlah_tanaman' || key == 'ketinggian_mdpl';
    return TextFormField(
      controller: _controllers[key],
      maxLines: lines,
      keyboardType: numeric
          ? TextInputType.numberWithOptions(decimal: !isInteger, signed: true)
          : TextInputType.text,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        alignLabelWithHint: lines > 1,
      ),
      validator: (value) {
        final text = value?.trim() ?? '';
        if (required && text.isEmpty) return 'Wajib diisi';
        if (numeric && text.isNotEmpty && double.tryParse(text) == null) {
          return 'Masukkan angka yang valid';
        }
        return null;
      },
    );
  }
}
