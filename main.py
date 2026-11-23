import os
import json
import shutil
import zipfile
import threading
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector

import requests
import cv2
import numpy as np
import tensorflow as tf
from PIL import Image, ImageOps

import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from auth_backend import auth_bp, device_required, login_required
from ai_backend import create_ai_routes

# =====================================================
# INISIALISASI FLASK & CORS
# =====================================================
app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
lock = threading.Lock()

# =====================================================
# INISIALISASI FIREBASE
# =====================================================
# Memuat konfigurasi dari file .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Konfigurasi database MySQL
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# Fungsi koneksi MySQL
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
# KONFIGURASI PATH & SERVER
# =====================================================
MODEL_PATH = os.path.join(BASE_DIR, "model", "best_mobilenetv2_strawberry.keras")
LABELS_PATH = os.path.join(BASE_DIR, "model", "labels.json")

DISEASE_MODEL_PATH = os.path.join(BASE_DIR, "model", "mobilenetv2_penyakit_daun.keras")
DISEASE_LABELS_PATH = os.path.join(BASE_DIR, "model", "class_names_daun.json")

STATIC_DIR = os.path.join(BASE_DIR, "static")
LATEST_IMAGE = os.path.join(STATIC_DIR, "latest.jpg")
LATEST_CROP_IMAGE = os.path.join(STATIC_DIR, "latest_crop.jpg")

os.makedirs(STATIC_DIR, exist_ok=True)

# Konfigurasi perangkat dari .env
ESP32_IP = os.getenv("ESP32_IP", "").strip().rstrip("/")

# =====================================================
# HELPER KOMPATIBILITAS KERAS (HAPUS quantization_config)
# =====================================================
def _strip_quantization_config(obj):
    if isinstance(obj, dict):
        obj.pop("quantization_config", None)
        for v in obj.values():
            _strip_quantization_config(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_quantization_config(item)

def load_keras_model_safe(model_path):
    try:
        return tf.keras.models.load_model(model_path, compile=False)
    except (TypeError, ValueError) as err:
        if "quantization_config" not in str(err):
            raise
        print(f"Menyesuaikan kompatibilitas Keras untuk {os.path.basename(model_path)}...")
        backup_path = model_path + ".bak"
        temp_path = model_path + ".tmp"
        if not os.path.exists(backup_path):
            shutil.copy2(model_path, backup_path)

        with zipfile.ZipFile(model_path, "r") as zin, zipfile.ZipFile(
            temp_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                content = zin.read(item.filename)
                if item.filename == "config.json":
                    cfg = json.loads(content.decode("utf-8"))
                    _strip_quantization_config(cfg)
                    content = json.dumps(cfg).encode("utf-8")
                zout.writestr(item, content)

        os.replace(temp_path, model_path)
        return tf.keras.models.load_model(model_path, compile=False)

# =====================================================
# MUAT MODEL & LABEL (BUAH + PENYAKIT DAUN)
# =====================================================
if os.path.exists(LABELS_PATH):
    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        labels_data = json.load(f)
    CLASS_NAMES = (
        labels_data
        if isinstance(labels_data, list)
        else [labels_data[str(i)] for i in range(len(labels_data))]
    )
else:
    CLASS_NAMES = ["matang", "medium", "mentah"]

if os.path.exists(DISEASE_LABELS_PATH):
    with open(DISEASE_LABELS_PATH, "r", encoding="utf-8") as f:
        disease_labels_data = json.load(f)
    DISEASE_CLASS_NAMES = (
        disease_labels_data
        if isinstance(disease_labels_data, list)
        else [disease_labels_data[str(i)] for i in range(len(disease_labels_data))]
    )
    print(f"Label Penyakit Daun dimuat ({len(DISEASE_CLASS_NAMES)} kelas):", DISEASE_CLASS_NAMES)
else:
    DISEASE_CLASS_NAMES = ["healthy", "leaf_scorch"]
    print("Peringatan: class_names_daun.json tidak ditemukan, memakai label default.")

print("Memuat model Kematangan Buah (MobileNetV2)...")
model = load_keras_model_safe(MODEL_PATH)
INPUT_HEIGHT = int(model.input_shape[1] or 224)
INPUT_WIDTH = int(model.input_shape[2] or 224)
print(f"Model Kematangan Buah berhasil dimuat! Input: {INPUT_WIDTH}x{INPUT_HEIGHT}")

disease_model = None
DISEASE_INPUT_HEIGHT = 224
DISEASE_INPUT_WIDTH = 224

if os.path.exists(DISEASE_MODEL_PATH):
    print("Memuat model Penyakit Daun (MobileNetV2)...")
    disease_model = load_keras_model_safe(DISEASE_MODEL_PATH)
    DISEASE_INPUT_HEIGHT = int(disease_model.input_shape[1] or 224)
    DISEASE_INPUT_WIDTH = int(disease_model.input_shape[2] or 224)
    disease_output_count = int(disease_model.output_shape[-1])
    if disease_output_count != len(DISEASE_CLASS_NAMES):
        disease_model = None
        raise RuntimeError(
            "Model penyakit daun memiliki "
            f"{disease_output_count} kelas, tetapi class_names_daun.json "
            f"memuat {len(DISEASE_CLASS_NAMES)} label."
        )
    print(f"Model Penyakit Daun berhasil dimuat! Input: {DISEASE_INPUT_WIDTH}x{DISEASE_INPUT_HEIGHT}")
else:
    print("Info: File mobilenetv2_penyakit_daun.keras belum ditemukan di folder model/.")

# =====================================================
# STATE VARIABEL (KAMERA, SENSOR & KONTROL RELAY)
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
    "versi_model_daun": "mobilenetv2_penyakit_daun.keras"
}

latest_sensor = {
    "suhu": 0.0,
    "kelembapan_tanah": 0,
    "kipas": "OFF",
    "pompa": "OFF",
    "mode": "AUTO",
    "waktu": "-"
}

control_state = {
    "mode": "AUTO",
    "kipas_manual": "OFF",
    "pompa_manual": "OFF",
    "kipas_pulse": False,
    "pompa_pulse": False
}

app.register_blueprint(auth_bp)
app.register_blueprint(
    create_ai_routes(
        lambda: {"sensor": latest_sensor, "diagnosis": latest_result}
    )
)

# =====================================================
# FUNGSI PREDIKSI PENYAKIT DAUN
# =====================================================
def predict_leaf_disease(pil_img):
    if disease_model is None:
        return "Model Daun Belum Dimuat", 0.0, {}

    # Model sudah berisi Rescaling; gunakan piksel RGB 0-255 tanpa filter tambahan.
    rgb = np.asarray(
        pil_img.convert("RGB").resize(
            (DISEASE_INPUT_WIDTH, DISEASE_INPUT_HEIGHT),
            Image.Resampling.BILINEAR,
        ),
        dtype=np.float32,
    )
    leaf_array = rgb[None]

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

    # Jangan ubah nama sehat/bukan-daun menjadi teks lain.
    if raw_label in ("sehat", "bukan_daun"):
        clean_label = raw_label
        if leaf_conf < 55.0 or margin < 10.0:
            clean_label = "Tidak yakin"
    elif leaf_conf < 60.0 or margin < 15.0:
        clean_label = "Tidak yakin"
    else:
        clean_label = raw_label

    probs = {
        DISEASE_CLASS_NAMES[i]: round(float(leaf_preds[i]) * 100, 2)
        for i in range(min(len(DISEASE_CLASS_NAMES), len(leaf_preds)))
    }
    return clean_label, leaf_conf, probs

# =====================================================
# FUNGSI OPENCV AUTO-CROP (HYBRID + ANTI OVER-ZOOM)
# =====================================================
def auto_crop_strawberry(img_bgr, min_area=500):
    img_h, img_w, _ = img_bgr.shape
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 100, 50])
    upper_red1 = np.array([12, 255, 245])
    lower_red2 = np.array([168, 100, 50])
    upper_red2 = np.array([179, 255, 245])

    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = cv2.bitwise_or(mask_red1, mask_red2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = w / float(h)
        if 0.45 <= aspect_ratio <= 2.0 and w < (img_w * 0.80):
            valid_contours.append((area, cnt))

    if valid_contours:
        _, best_contour = max(valid_contours, key=lambda item: item[0])
        x, y, w, h = cv2.boundingRect(best_contour)

        pad_left = int(w * 0.45)
        pad_right = int(w * 0.45)
        pad_top = int(h * 0.65)
        pad_bottom = int(h * 0.25)

        x1 = max(0, x - pad_left)
        y1 = max(0, y - pad_top)
        x2 = min(img_w, x + w + pad_right)
        y2 = min(img_h, y + h + pad_bottom)

        min_w = int(img_w * 0.55)
        min_h = int(img_h * 0.55)

        if (x2 - x1) < min_w:
            cx = (x1 + x2) // 2
            x1 = max(0, cx - min_w // 2)
            x2 = min(img_w, x1 + min_w)

        if (y2 - y1) < min_h:
            cy = (y1 + y2) // 2
            y1 = max(0, cy - min_h // 2)
            y2 = min(img_h, y1 + min_h)

        return img_bgr[y1:y2, x1:x2]

    margin_x = int(img_w * 0.18)
    margin_y = int(img_h * 0.18)
    return img_bgr[margin_y:img_h - margin_y, margin_x:img_w - margin_x]

# =====================================================
# RUTE FLASK (HALAMAN WEB & DETEKSI BUAH + DAUN)
# =====================================================
@app.route("/")
def home():
    return render_template("index.html")

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
        raw_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # JALUR A: DETEKSI PENYAKIT DAUN (FULL FRAME)
        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)

        # JALUR B: DETEKSI KEMATANGAN BUAH (OPENCV AUTO-CROP)
        cropped_bgr = auto_crop_strawberry(raw_bgr)
        if cropped_bgr is not None:
            cv2.imwrite(LATEST_CROP_IMAGE, cropped_bgr)
            crop_rgb = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2RGB)
            img_for_fruit = Image.fromarray(crop_rgb)
            crop_detected = True
        else:
            img_for_fruit = img
            crop_detected = False

        img_resized = img_for_fruit.resize((INPUT_WIDTH, INPUT_HEIGHT), Image.Resampling.LANCZOS)
        image_array = np.expand_dims(np.asarray(img_resized, dtype=np.float32) / 255.0, axis=0)

        with lock:
            predictions = model.predict(image_array, verbose=0)

        probabilities = predictions[0]
        predicted_index = int(np.argmax(probabilities))
        confidence = float(probabilities[predicted_index])

        if confidence < 0.40:
            predicted_class = "Tidak Diketahui"
        else:
            predicted_class = CLASS_NAMES[predicted_index]

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
            "probabilities": {CLASS_NAMES[i]: round(float(probabilities[i]), 6) for i in range(len(CLASS_NAMES))}
        }
        latest_result = result

        try:
            ref = db.reference("riwayat_strawberry")
            ref.push({
                "waktu": waktu_sekarang,
                "kelas": predicted_class,
                "confidence": round(confidence * 100, 2),
                "penyakit_daun": leaf_status,
                "penyakit_confidence": leaf_conf
            })
            print(
                f"[{waktu_sekarang}] Buah: {predicted_class} ({round(confidence * 100, 2)}%) | "
                f"Daun: {leaf_status} ({leaf_conf}%)"
            )
        except Exception as fb_err:
            print("Gagal Firebase:", fb_err)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/latest", methods=["GET"])
@login_required
def api_latest():
    payload = dict(latest_result)
    payload["sensor"] = latest_sensor
    if os.path.exists(LATEST_IMAGE) and "image_url" not in payload:
        payload["image_url"] = f"/static/latest.jpg?t={int(os.path.getmtime(LATEST_IMAGE))}"
    if os.path.exists(LATEST_CROP_IMAGE) and "cropped_url" not in payload:
        payload["cropped_url"] = f"/static/latest_crop.jpg?t={int(os.path.getmtime(LATEST_CROP_IMAGE))}"
    return jsonify(payload)

@app.route("/api/capture", methods=["GET", "POST"])
@login_required
def trigger_capture():
    try:
        esp32_url = f"{ESP32_IP}/capture"
        response = requests.get(esp32_url, timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Perintah terkirim"})
        else:
            return jsonify({"status": "error", "error": "ESP32 error"}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": "Gagal menghubungi ESP32"}), 500

# =====================================================
# RUTE FLASK (DETEKSI DAUN VIA MOBILE FLUTTER)
# =====================================================
@app.route("/api/predict-disease", methods=["POST"])
@login_required
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
        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)

        return jsonify({
            "status": "success",
            "model": "MobileNetV2",
            "versi_model": "mobilenetv2_penyakit_daun.keras",
            "penyakit_daun": leaf_status,
            "confidence": leaf_conf,
            "probabilities": leaf_probs
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# =====================================================
# RUTE FLASK (SENSOR & KONTROL RELAY ESP8266)
# =====================================================
@app.route("/api/control", methods=["GET", "POST"])
@login_required
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
@login_required
def sensor_read():
    return jsonify(latest_sensor), 200


@app.post("/api/sensor")
@device_required
def sensor_receive():
    global latest_sensor, control_state
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with lock:
            cmd_to_esp = {
                "mode": control_state["mode"],
                "kipas_manual": control_state["kipas_manual"],
                "pompa_manual": control_state["pompa_manual"],
                "kipas_pulse": control_state["kipas_pulse"],
                "pompa_pulse": control_state["pompa_pulse"]
            }
            control_state["kipas_pulse"] = False
            control_state["pompa_pulse"] = False

            latest_sensor = {
                "suhu": round(float(data.get("suhu", 0)), 1),
                "kelembapan_tanah": int(data.get("kelembapan_tanah", 0)),
                "kipas": str(data.get("kipas", "OFF")).upper(),
                "pompa": str(data.get("pompa", "OFF")).upper(),
                "mode": control_state["mode"],
                "waktu": waktu_sekarang
            }

        try:
            db.reference("sensor_greenhouse/latest").set(latest_sensor)
        except Exception as fb_err:
            print("Gagal simpan sensor ke Firebase:", fb_err)

        return jsonify({"status": "success", "control": cmd_to_esp}), 200

    return jsonify(latest_sensor), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)