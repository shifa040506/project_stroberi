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
LEAF_ROI_DEBUG_DIR = os.path.join(BASE_DIR, "static", "roi_debug", "leaf")
os.makedirs(LEAF_ROI_DEBUG_DIR, exist_ok=True)

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


def compute_leaf_roi_steps(img_bgr, min_area=450):
    img_h, img_w = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([20, 30, 30]), np.array([100, 255, 255]))

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [
        (cv2.contourArea(contour), contour)
        for contour in contours
        if min_area <= cv2.contourArea(contour) <= img_w * img_h * 0.9
    ]

    if candidates:
        area, contour = max(candidates, key=lambda candidate: candidate[0])
        x, y, w, h = cv2.boundingRect(contour)
        x1 = max(0, x - int(w * 0.15))
        y1 = max(0, y - int(h * 0.15))
        x2 = min(img_w, x + w + int(w * 0.15))
        y2 = min(img_h, y + h + int(h * 0.15))
        return {
            "method": "HSV Daun + Morfologi",
            "crop_detected": True,
            "contour_area": round(float(area), 1),
            "raw_box": (x, y, x + w, y + h),
            "final_box": (x1, y1, x2, y2),
            "mask": mask,
            "cropped_bgr": img_bgr[y1:y2, x1:x2],
        }

    return {
        "method": "Crop Manual (fallback)",
        "crop_detected": False,
        "contour_area": 0,
        "raw_box": None,
        "final_box": (0, 0, img_w, img_h),
        "mask": mask,
        "cropped_bgr": img_bgr,
    }


def predict_leaf_disease(pil_img):
    if disease_model is None:
        return "Model Daun Belum Dimuat", 0.0, {}

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


@leaf_mobile_bp.route("/api/roi/leaf/process", methods=["POST"])
def process_leaf_roi():
    try:
        uploaded = request.files.get("file")
        if uploaded is None or uploaded.filename == "":
            return jsonify({"status": "error", "error": "File crop daun tidak ditemukan."}), 400

        img = ImageOps.exif_transpose(Image.open(uploaded.stream)).convert("RGB")
        raw_bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        roi_data = compute_leaf_roi_steps(raw_bgr)

        bbox_vis = raw_bgr.copy()
        if roi_data["raw_box"] is not None:
            rx1, ry1, rx2, ry2 = roi_data["raw_box"]
            cv2.rectangle(bbox_vis, (rx1, ry1), (rx2, ry2), (0, 255, 255), 2)
        fx1, fy1, fx2, fy2 = roi_data["final_box"]
        cv2.rectangle(bbox_vis, (fx1, fy1), (fx2, fy2), (0, 255, 0), 3)

        ts = int(datetime.now().timestamp() * 1000)
        debug_images = {
            "original": raw_bgr,
            "mask": roi_data["mask"],
            "bbox": bbox_vis,
            "crop": roi_data["cropped_bgr"],
        }
        image_urls = {}
        for name, image in debug_images.items():
            filename = f"step_{name}_{ts}.jpg"
            if not cv2.imwrite(os.path.join(LEAF_ROI_DEBUG_DIR, filename), image):
                raise OSError(f"Gagal menyimpan visualisasi ROI daun: {filename}")
            image_urls[name] = f"/static/roi_debug/leaf/{filename}"

        cropped_rgb = cv2.cvtColor(roi_data["cropped_bgr"], cv2.COLOR_BGR2RGB)
        leaf_status, confidence, probabilities = predict_leaf_disease(Image.fromarray(cropped_rgb))

        return jsonify({
            "status": "success",
            "data": {
                "method": roi_data["method"],
                "crop_detected": roi_data["crop_detected"],
                "contour_area": roi_data["contour_area"],
                "final_box": list(roi_data["final_box"]),
                "penyakit_daun": leaf_status,
                "confidence_percent": confidence,
                "probabilities": probabilities,
                "images": image_urls,
            },
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


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