import os
from io import BytesIO
from datetime import datetime
import requests
from PIL import Image, ImageOps
from flask import Blueprint, request, jsonify
from firebase_admin import db

from auth_backend import device_required
from roi_backend import predict_fruit_ripeness
from leaf_mobile_backend import predict_leaf_disease
from state import (
    LATEST_IMAGE,
    LATEST_CROP_IMAGE,
    LATEST_CROP_DAUN_IMAGE,
    latest_result,
    latest_sensor,
)

camera_bp = Blueprint("camera", __name__)

@camera_bp.route("/predict", methods=["POST"])
@device_required
def predict():
    try:
        img = None
        if "file" in request.files and request.files["file"].filename != "":
            img = Image.open(request.files["file"].stream)
        elif "image" in request.files and request.files["image"].filename != "":
            img = Image.open(request.files["image"].stream)
        elif request.data:
            img = Image.open(BytesIO(request.data))
        else:
            return jsonify({"error": "File gambar tidak ditemukan."}), 400

        img = ImageOps.exif_transpose(img).convert("RGB")
        img.save(LATEST_IMAGE, format="JPEG", quality=95)

        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)
        predicted_class, confidence, crop_detected, fruit_probs = predict_fruit_ripeness(img)

        waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ts_cache = int(datetime.now().timestamp())

        result = {
            "status": "success",
            "waktu": waktu_sekarang,
            "model": "MobileNetV2",
            "versi_model_daun": "mobilenetv2_penyakit_daun.keras",
            "kelas": predicted_class,
            "confidence": confidence,
            "confidence_percent": round(confidence * 100, 2),
            "crop_detected": crop_detected,
            "penyakit_daun": leaf_status,
            "penyakit_confidence": leaf_conf,
            "disease_confidence": leaf_conf,
            "disease_probabilities": leaf_probs,
            "image_url": f"/static/latest.jpg?t={ts_cache}",
            "cropped_url": f"/static/latest_crop.jpg?t={ts_cache}",
            "probabilities": fruit_probs,
        }
        latest_result.clear()
        latest_result.update(result)

        try:
            db.reference("riwayat_strawberry").push({
                "waktu": waktu_sekarang,
                "kelas": predicted_class,
                "confidence": round(confidence * 100, 2),
                "penyakit_daun": leaf_status,
                "penyakit_confidence": leaf_conf,
            })
        except Exception as fb_err:
            print("Gagal Firebase:", fb_err)

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@camera_bp.route("/api/latest", methods=["GET"])
def api_latest():
    payload = dict(latest_result)
    payload["sensor"] = latest_sensor
    if os.path.exists(LATEST_IMAGE) and "image_url" not in payload:
        payload["image_url"] = f"/static/latest.jpg?t={int(os.path.getmtime(LATEST_IMAGE))}"
    if os.path.exists(LATEST_CROP_IMAGE) and "cropped_url" not in payload:
        payload["cropped_url"] = f"/static/latest_crop.jpg?t={int(os.path.getmtime(LATEST_CROP_IMAGE))}"
    if os.path.exists(LATEST_CROP_DAUN_IMAGE) and "leaf_cropped_url" not in payload:
        payload["leaf_cropped_url"] = f"/static/latest_crop_daun.jpg?t={int(os.path.getmtime(LATEST_CROP_DAUN_IMAGE))}"
    return jsonify(payload)

@camera_bp.route("/api/capture", methods=["GET", "POST"])
def trigger_capture():
    esp32_ip = os.getenv("ESP32_IP", "").strip().rstrip("/")
    try:
        response = requests.get(f"{esp32_ip}/capture", timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Perintah terkirim"})
        return jsonify({"status": "error", "error": "ESP32 error"}), 400
    except Exception:
        return jsonify({"status": "error", "error": "Gagal menghubungi ESP32"}), 500