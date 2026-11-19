import 'package:flutter/material.dart';

// Nama tampilan untuk tiap kelas dari model. Kelas yang tidak ada di daftar ini
// tetap tampil (underscore diganti spasi), jadi menambah kelas baru tidak merusak aplikasi.
const Map<String, String> _nama = {
  'sehat': 'Daun sehat',
  'bukan_daun': 'Bukan daun',
  'angular_leafspot': 'Bercak sudut (angular leaf spot)',
  'anthracnose_fruit_rot': 'Busuk buah antraknosa',
  'blossom_blight': 'Hawar bunga (blossom blight)',
  'gray_mold': 'Kapang abu-abu (gray mold)',
  'leaf_spot': 'Bercak daun (leaf spot)',
  'powdery_mildew_fruit': 'Embun tepung pada buah',
  'powdery_mildew_leaf': 'Embun tepung pada daun',
};

String namaKelas(String? k) {
  if (k == null || k.isEmpty) return '-';
  if (_nama.containsKey(k)) return _nama[k]!;
  final s = k.replaceAll('_', ' ');
  return s[0].toUpperCase() + s.substring(1);
}

String alasanTeks(String? a) {
  switch (a) {
    case 'kemiripan_rendah':
      return 'Gambar tidak mirip dengan foto daun stroberi yang dikenal model. '
          'Pastikan yang difoto adalah daun, jelas, dan tidak terlalu jauh.';
    case 'kepercayaan_rendah':
      return 'Model kurang yakin dengan hasilnya. Coba foto ulang dengan cahaya lebih baik.';
    case 'selisih_top2_tipis':
      return 'Dua kemungkinan hampir sama kuat, jadi hasil tidak bisa dipastikan.';
    default:
      return a ?? 'Hasil tidak dapat dipastikan.';
  }
}

Color warnaKelas(String? k) {
  if (k == 'sehat') return Colors.green;
  if (k == 'bukan_daun') return Colors.blueGrey;
  return Colors.deepOrange;
}
