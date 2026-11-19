double _d(dynamic v) => (v as num?)?.toDouble() ?? 0.0;

class Top {
  final String kelas;
  final double prob;
  Top(this.kelas, this.prob);
  factory Top.fromJson(Map<String, dynamic> j) =>
      Top(j['kelas'] as String, _d(j['prob']));
}

/// Hasil prediksi satu foto
class Prediksi {
  final String status; // "diterima" | "ditolak"
  final String? hasil;
  final String? alasan;
  final String tebakan;
  final double kepercayaan;
  final double kemiripan;
  final List<Top> top3;
  final String versi;
  final double waktuMs;

  Prediksi({
    required this.status,
    required this.hasil,
    required this.alasan,
    required this.tebakan,
    required this.kepercayaan,
    required this.kemiripan,
    required this.top3,
    required this.versi,
    required this.waktuMs,
  });

  bool get diterima => status == 'diterima';

  /// Jawaban FastAPI /predict
  factory Prediksi.fromJson(Map<String, dynamic> j) => Prediksi(
    status: j['status'] as String,
    hasil: j['hasil'] as String?,
    alasan: j['alasan_ditolak'] as String?,
    tebakan: j['tebakan_teratas'] as String? ?? '',
    kepercayaan: _d(j['kepercayaan']),
    kemiripan: _d(j['kemiripan']),
    top3: ((j['top3'] as List?) ?? [])
        .map((e) => Top.fromJson(e as Map<String, dynamic>))
        .toList(),
    versi: j['versi_model']?.toString() ?? '-',
    waktuMs: _d(j['waktu_ms']),
  );

  /// Jawaban Flask /api/predict-disease: {status, penyakit_daun, confidence (persen), probabilities (persen)}
  factory Prediksi.fromFlask(Map<String, dynamic> j) {
    final probs = <String, double>{};
    (j['probabilities'] as Map? ?? {}).forEach(
      (k, v) => probs[k.toString()] = _d(v) / 100.0,
    );
    final urut = probs.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final label = (j['penyakit_daun'] ?? '').toString();
    final yakin =
        label.isNotEmpty &&
        label != 'Tidak yakin' &&
        label != 'Model Daun Belum Dimuat';
    final teratas = urut.isNotEmpty ? urut.first.key : '';
    return Prediksi(
      status: yakin ? 'diterima' : 'ditolak',
      hasil: yakin ? teratas : null,
      alasan: yakin ? null : 'kepercayaan_rendah',
      tebakan: teratas,
      kepercayaan: _d(j['confidence']) / 100.0,
      kemiripan: 0,
      top3: urut.take(3).map((e) => Top(e.key, e.value)).toList(),
      versi: 'Flask',
      waktuMs: 0,
    );
  }
}

/// Satu baris riwayat (belum dipakai oleh server Flask)
class RiwayatItem {
  final int id;
  final String waktu;
  final String perangkat;
  final String status;
  final String? hasil;
  final String? alasan;
  final double kepercayaan;

  RiwayatItem({
    required this.id,
    required this.waktu,
    required this.perangkat,
    required this.status,
    required this.hasil,
    required this.alasan,
    required this.kepercayaan,
  });

  bool get diterima => status == 'diterima';

  factory RiwayatItem.fromJson(Map<String, dynamic> j) => RiwayatItem(
    id: (j['id'] as num?)?.toInt() ?? 0,
    waktu: j['waktu']?.toString() ?? '',
    perangkat: j['perangkat']?.toString() ?? '',
    status: j['status']?.toString() ?? '',
    hasil: j['hasil'] as String?,
    alasan: j['alasan'] as String?,
    kepercayaan: _d(j['kepercayaan']),
  );
}
