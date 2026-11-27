import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

LATEST_IMAGE = os.path.join(STATIC_DIR, "latest.jpg")
LATEST_CROP_IMAGE = os.path.join(STATIC_DIR, "latest_crop.jpg")
LATEST_CROP_DAUN_IMAGE = os.path.join(STATIC_DIR, "latest_crop_daun.jpg")

lock = threading.Lock()

latest_result = {
    "status": "waiting",
    "kelas": "-",
    "confidence": 0,
    "confidence_percent": 0,
    "penyakit_daun": "Menunggu Gambar",
    "penyakit_confidence": 0,
    "disease_confidence": 0,
    "model": "MobileNetV2",
}

latest_sensor = {
    "suhu": 0.0,
    "kelembapan_tanah": 0,
    "kipas": "OFF",
    "pompa": "OFF",
    "mode": "AUTO",
    "waktu": "-",
}

control_state = {
    "mode": "AUTO",
    "kipas_manual": "OFF",
    "pompa_manual": "OFF",
    "kipas_pulse": False,
    "pompa_pulse": False,
}