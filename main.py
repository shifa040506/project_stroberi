import os
import json
import threading
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector

import requests
import cv2
import numpy as np
from PIL import Image, ImageOps

import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify
from flask_cors import CORS

from auth_backend import auth_bp, device_required, login_required
from ai_backend import create_ai_routes
from roi_backend import roi_bp, load_keras_model_safe, predict_fruit_ripeness
from web_backend import web_bp

# =====================================================
# INISIALISASI FLASK & CORS
# =====================================================
app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# =====================================================
# KONEKSI MYSQL & FIREBASE
# =====================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

try:
    conn = get_db_connection()
    print("Koneksi MySQL berhasil!")
    conn.close()
except Exception as e:
    print("Koneksi MySQL gagal:", e)

try:
    firebase_credentials = {
        "type": "service_account",
        "project_id": os.getenv("FIREBASE_PROJECT_ID", ""),
        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
        "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL", ""),
        "client_id": os.getenv("FIREBASE_CLIENT_ID", ""),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    FIREBASE_DB_URL = os.getenv("FIREBASE_DATABASE_URL", "").strip()
    if not FIREBASE_DB_URL or not all((
        firebase_credentials["project_id"],
        firebase_credentials["private_key"],
        firebase_credentials["client_email"],
    )):
        raise RuntimeError("Konfigurasi Firebase belum lengkap di .env.")
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    print("Firebase berhasil diinisialisasi!")
except Exception as e:
    print("Gagal inisialisasi Firebase:", e)

# =====================================================
# KONFIGURASI PATH & MODEL PENYAKIT DAUN
# =====================================================
DISEASE_MODEL_PATH = os.path.join(BASE_DIR, "model", "mobilenetv2_penyakit_daun.keras")
DISEASE_LABELS_PATH = os.path.join(BASE_DIR, "model", "class_names_daun.json")

STATIC_DIR = os.path.join(BASE_DIR, "static")
LATEST_IMAGE = os.path.join(STATIC_DIR, "latest.jpg")
LATEST_CROP_IMAGE = os.path.join(STATIC_DIR, "latest_crop.jpg")
os.makedirs(STATIC_DIR, exist_ok=True)

ESP32_IP = os.getenv("ESP32_IP", "").strip().rstrip("/")

if os.path.exists(DISEASE_LABELS_PATH):
    with open(DISEASE_LABELS_PATH, "r", encoding="utf-8") as f:
        disease_labels_data = json.load(f)
    DISEASE_CLASS_NAMES = (
        disease_labels_data
        if isinstance(disease_labels_data, list)
        else [disease_labels_data[str(i)] for i in range(len(disease_labels_data))]
    )
else:
    DISEASE_CLASS_NAMES = ["healthy", "leaf_scorch"]

disease_model = None
DISEASE_INPUT_HEIGHT = 224
DISEASE_INPUT_WIDTH = 224

if os.path.exists(DISEASE_MODEL_PATH):
    disease_model = load_keras_model_safe(DISEASE_MODEL_PATH)
    DISEASE_INPUT_HEIGHT = int(disease_model.input_shape[1] or 224)
    DISEASE_INPUT_WIDTH = int(disease_model.input_shape[2] or 224)

# =====================================================
# STATE VARIABEL & REGISTRASI BLUEPRINT
# =====================================================
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

app.register_blueprint(auth_bp)
app.register_blueprint(
    create_ai_routes(
        lambda: {"sensor": latest_sensor, "diagnosis": latest_result}
    )
)
app.register_blueprint(roi_bp)   # Blueprint ROI & Model Buah
app.register_blueprint(web_bp)   # Blueprint Web Pembuatan Akun User

# =====================================================
# FUNGSI PREDIKSI PENYAKIT DAUN
# =====================================================
def predict_leaf_disease(pil_img):
    if disease_model is None:
        return "Model Daun Belum Dimuat", 0.0, {}

    bgr = cv2.cvtColor(np.asarray(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    bgr = cv2.resize(bgr, (DISEASE_INPUT_WIDTH, DISEASE_INPUT_HEIGHT), interpolation=cv2.INTER_AREA)
    bgr = cv2.GaussianBlur(bgr, (3, 3), 0)
    leaf_array = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)[None]

    with lock:
        leaf_preds = disease_model.predict(leaf_array, verbose=0)[0]

    order = np.argsort(leaf_preds)[::-1]
    leaf_idx = int(order[0])

    # Pemetaan tegas untuk dua kelas yang rentan tertukar/salah indeks.
    DISEASE_INDEX_OVERRIDE = {
        3: "bukan_daun",
        8: "sehat",
    }
    raw_label = DISEASE_INDEX_OVERRIDE.get(
        leaf_idx,
        DISEASE_CLASS_NAMES[leaf_idx]
        if leaf_idx < len(DISEASE_CLASS_NAMES)
        else f"class_{leaf_idx}",
    )
    leaf_conf = round(float(leaf_preds[leaf_idx]) * 100, 2)
    margin = float(leaf_preds[order[0]] - leaf_preds[order[1]]) * 100

    clean_label = "Tidak yakin" if (leaf_conf < 60.0 or margin < 15.0) else raw_label.replace("_", " ").title()
    probs = {
        DISEASE_CLASS_NAMES[i]: round(float(leaf_preds[i]) * 100, 2)
        for i in range(min(len(DISEASE_CLASS_NAMES), len(leaf_preds)))
    }
    return clean_label, leaf_conf, probs

# =====================================================
# RUTE INTEGRASI KAMERA, MOBILE, & SENSOR IOT
# =====================================================
@app.route("/predict", methods=["POST"])
@device_required
def predict():
    global latest_result
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

        # Jalur A: Penyakit Daun
        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)

        # Jalur B: ROI + Kematangan Buah (dipanggil dari roi_backend.py)
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
        latest_result = result

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

@app.route("/api/latest", methods=["GET"])
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

@app.route("/api/capture", methods=["GET", "POST"])
def trigger_capture():
    try:
        response = requests.get(f"{ESP32_IP}/capture", timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Perintah terkirim"})
        return jsonify({"status": "error", "error": "ESP32 error"}), 400
    except Exception:
        return jsonify({"status": "error", "error": "Gagal menghubungi ESP32"}), 500

@app.route("/api/predict-disease", methods=["POST"])
def predict_disease_mobile():
    try:
        img = None
        if "file" in request.files and request.files["file"].filename != "":
            img = Image.open(request.files["file"].stream)
        elif "image" in request.files and request.files["image"].filename != "":
            img = Image.open(request.files["image"].stream)
        else:
            return jsonify({"error": "File gambar tidak ditemukan."}), 400

        img = ImageOps.exif_transpose(img).convert("RGB")
        img.save(LATEST_CROP_DAUN_IMAGE, format="JPEG", quality=95)
        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)
        ts_cache = int(datetime.now().timestamp())

        return jsonify({
            "status": "success",
            "model": "MobileNetV2",
            "versi_model": "mobilenetv2_penyakit_daun.keras",
            "penyakit_daun": leaf_status,
            "confidence": leaf_conf,
            "probabilities": leaf_probs,
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/control", methods=["GET", "POST"])
def handle_control():
    global control_state, latest_sensor
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        device = str(data.get("device", "")).lower()
        action = str(data.get("action", "")).upper()

        with lock:
            if action == "AUTO":
                control_state["mode"] = "AUTO"
                latest_sensor["mode"] = "AUTO"
            elif action == "PULSE_1S":
                if device == "kipas":
                    control_state["kipas_pulse"] = True
                    latest_sensor["kipas"] = "ON (1s)"
                elif device == "pompa":
                    control_state["pompa_pulse"] = True
                    latest_sensor["pompa"] = "ON (1s)"
            elif action in ["ON", "OFF"]:
                control_state["mode"] = "MANUAL"
                latest_sensor["mode"] = "MANUAL"
                if device == "kipas":
                    control_state["kipas_manual"] = action
                    latest_sensor["kipas"] = action
                elif device == "pompa":
                    control_state["pompa_manual"] = action
                    latest_sensor["pompa"] = action

        return jsonify({"status": "success", "control": control_state}), 200
    return jsonify(control_state), 200

@app.get("/api/sensor")
def sensor_read():
    return jsonify(latest_sensor), 200

@app.post("/api/sensor")
@device_required
def sensor_receive():
    global latest_sensor, control_state
    data = request.get_json(silent=True) or {}
    waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with lock:
        cmd_to_esp = {
            "mode": control_state["mode"],
            "kipas_manual": control_state["kipas_manual"],
            "pompa_manual": control_state["pompa_manual"],
            "kipas_pulse": control_state["kipas_pulse"],
            "pompa_pulse": control_state["pompa_pulse"],
        }
        control_state["kipas_pulse"] = False
        control_state["pompa_pulse"] = False

        latest_sensor = {
            "suhu": round(float(data.get("suhu", 0)), 1),
            "kelembapan_tanah": int(data.get("kelembapan_tanah", 0)),
            "kipas": str(data.get("kipas", "OFF")).upper(),
            "pompa": str(data.get("pompa", "OFF")).upper(),
            "mode": control_state["mode"],
            "waktu": waktu_sekarang,
        }

    try:
        db.reference("sensor_greenhouse/latest").set(latest_sensor)
    except Exception as fb_err:
        print("Gagal simpan sensor ke Firebase:", fb_err)

    return jsonify({"status": "success", "control": cmd_to_esp}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)