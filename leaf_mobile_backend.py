import os
import json
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageOps
from flask import Blueprint, request, jsonify

from roi_backend import load_keras_model_safe, predict_fruit_ripeness
from state import BASE_DIR, LATEST_IMAGE, LATEST_CROP_DAUN_IMAGE, lock

leaf_mobile_bp = Blueprint("leaf_mobile", __name__)

DISEASE_MODEL_PATH = os.path.join(BASE_DIR, "model", "mobilenetv2_penyakit_daun.keras")
DISEASE_LABELS_PATH = os.path.join(BASE_DIR, "model", "class_names_daun.json")

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
    print(f"Model Penyakit Daun berhasil dimuat! Input: {DISEASE_INPUT_WIDTH}x{DISEASE_INPUT_HEIGHT}")
else:
    print("Info: File mobilenetv2_penyakit_daun.keras belum ditemukan di folder model/.")

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

@leaf_mobile_bp.route("/api/predict-disease", methods=["POST"])
def predict_disease_mobile():
    try:
        uploaded = request.files.get("file") or request.files.get("image")
        if uploaded is None or uploaded.filename == "":
            return jsonify({"error": "File gambar tidak ditemukan."}), 400

        img = ImageOps.exif_transpose(Image.open(uploaded.stream)).convert("RGB")
        img.save(LATEST_CROP_DAUN_IMAGE, format="JPEG", quality=95)
        leaf_status, leaf_conf, leaf_probs = predict_leaf_disease(img)

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

@leaf_mobile_bp.route("/api/predict-fruit", methods=["POST"])
def predict_fruit_mobile():
    try:
        uploaded = request.files.get("file") or request.files.get("image")
        if uploaded is None or uploaded.filename == "":
            return jsonify({"error": "File gambar tidak ditemukan."}), 400

        img = ImageOps.exif_transpose(Image.open(uploaded.stream)).convert("RGB")
        img.save(LATEST_IMAGE, format="JPEG", quality=95)

        fruit_class, confidence, crop_detected, probabilities = predict_fruit_ripeness(img)
        ts_cache = int(datetime.now().timestamp())

        return jsonify({
            "status": "success",
            "model": "MobileNetV2",
            "versi_model": "best_mobilenetv2_strawberry.keras",
            "kondisi_buah": fruit_class,
            "confidence": round(confidence * 100, 2),
            "crop_detected": crop_detected,
            "probabilities": probabilities,
            "image_url": f"/static/latest.jpg?t={ts_cache}",
            "cropped_url": f"/static/latest_crop.jpg?t={ts_cache}",
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500