import os
import json
import shutil
import zipfile
import threading
from datetime import datetime

import cv2
import numpy as np
import tensorflow as tf
from PIL import Image, ImageOps
from flask import Blueprint, request, jsonify, render_template

roi_bp = Blueprint("roi", __name__)
roi_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "best_mobilenetv2_strawberry.keras")
LABELS_PATH = os.path.join(BASE_DIR, "model", "labels.json")

STATIC_DIR = os.path.join(BASE_DIR, "static")
LATEST_IMAGE = os.path.join(STATIC_DIR, "latest.jpg")
LATEST_CROP_IMAGE = os.path.join(STATIC_DIR, "latest_crop.jpg")
ROI_DEBUG_DIR = os.path.join(STATIC_DIR, "roi_debug")
os.makedirs(ROI_DEBUG_DIR, exist_ok=True)


# =====================================================
# HELPER KOMPATIBILITAS & LOAD MODEL KEMATANGAN BUAH
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

print("Memuat model Kematangan Buah (MobileNetV2)...")
fruit_model = load_keras_model_safe(MODEL_PATH)
INPUT_HEIGHT = int(fruit_model.input_shape[1] or 224)
INPUT_WIDTH = int(fruit_model.input_shape[2] or 224)
print(f"Model Kematangan Buah siap! Input: {INPUT_WIDTH}x{INPUT_HEIGHT}")


# =====================================================
# LOGIKA INTI OPENCV ROI (MATANG, MEDIUM, & MENTAH)
# =====================================================
def compute_roi_steps(img_bgr, min_area=450):
    img_h, img_w, _ = img_bgr.shape
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    laplacian_abs = np.abs(cv2.Laplacian(gray, cv2.CV_64F))

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    # TAHAP 1: DETEKSI BUAH MATANG & MEDIUM (MERAH / ORANYE / PINK)
    mask_red1 = cv2.inRange(hsv, np.array([0, 90, 55]), np.array([18, 255, 255]))
    mask_red2 = cv2.inRange(hsv, np.array([165, 90, 55]), np.array([179, 255, 255]))
    mask_ripe = cv2.bitwise_or(mask_red1, mask_red2)
    mask_ripe = cv2.morphologyEx(mask_ripe, cv2.MORPH_OPEN, kernel_open)
    mask_ripe = cv2.morphologyEx(mask_ripe, cv2.MORPH_CLOSE, kernel_close)

    contours_ripe, _ = cv2.findContours(mask_ripe, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_candidates = []

    for cnt in contours_ripe:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = w / float(h)
        if 0.45 <= aspect_ratio <= 1.85 and w < (img_w * 0.75) and y < (img_h * 0.85):
            valid_candidates.append((area, cnt, mask_ripe, "HSV Matang/Medium"))

    # TAHAP 2: DETEKSI BUAH MENTAH (HIJAU KEKUNINGAN + TEKSTUR BIJI)
    if not valid_candidates:
        mask_unripe = cv2.inRange(hsv, np.array([20, 75, 95]), np.array([46, 255, 255]))
        mask_unripe = cv2.morphologyEx(mask_unripe, cv2.MORPH_OPEN, kernel_open)
        mask_unripe = cv2.morphologyEx(mask_unripe, cv2.MORPH_CLOSE, kernel_close)

        contours_unripe, _ = cv2.findContours(mask_unripe, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_unripe:
            area = cv2.contourArea(cnt)
            if area < min_area or area > (img_w * img_h * 0.45):
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)
            if not (0.55 <= aspect_ratio <= 1.65):
                continue

            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            solidity = area / float(hull_area) if hull_area > 0 else 0
            if solidity < 0.72:
                continue

            cnt_mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(cnt_mask, [cnt], -1, 255, -1)
            texture_score = cv2.mean(laplacian_abs, mask=cnt_mask)[0]
            if texture_score < 10.0:
                continue

            score = area * solidity * texture_score
            valid_candidates.append((score, cnt, mask_unripe, "HSV Mentah + Tekstur Biji"))

    # PEMOTONGAN ROI DENGAN PADDING PROPORSIONAL
    if valid_candidates:
        _, best_contour, active_mask, method_name = max(valid_candidates, key=lambda item: item[0])
        best_area = cv2.contourArea(best_contour)
        x, y, w, h = cv2.boundingRect(best_contour)

        x1 = max(0, x - int(w * 0.25))
        y1 = max(0, y - int(h * 0.40))
        x2 = min(img_w, x + w + int(w * 0.25))
        y2 = min(img_h, y + h + int(h * 0.20))

        min_w = int(img_w * 0.32)
        min_h = int(img_h * 0.32)

        if (x2 - x1) < min_w:
            cx = (x1 + x2) // 2
            x1 = max(0, cx - min_w // 2)
            x2 = min(img_w, x1 + min_w)

        if (y2 - y1) < min_h:
            cy = (y1 + y2) // 2
            y1 = max(0, cy - min_h // 2)
            y2 = min(img_h, y1 + min_h)

        return {
            "method": method_name,
            "crop_detected": True,
            "contour_area": round(float(best_area), 1),
            "raw_box": (x, y, x + w, y + h),
            "final_box": (x1, y1, x2, y2),
            "mask": active_mask,
            "cropped_bgr": img_bgr[y1:y2, x1:x2],
        }

    # FALLBACK CENTER CROP
    margin_x = int(img_w * 0.22)
    margin_y = int(img_h * 0.22)
    x1, y1, x2, y2 = margin_x, margin_y, img_w - margin_x, img_h - margin_y

    return {
        "method": "Fallback Center Crop",
        "crop_detected": False,
        "contour_area": 0,
        "raw_box": None,
        "final_box": (x1, y1, x2, y2),
        "mask": mask_ripe,
        "cropped_bgr": img_bgr[y1:y2, x1:x2],
    }


def _classify_cropped_bgr(cropped_bgr):
    crop_rgb = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2RGB)
    img_for_fruit = Image.fromarray(crop_rgb)
    img_resized = img_for_fruit.resize((INPUT_WIDTH, INPUT_HEIGHT), Image.Resampling.LANCZOS)
    image_array = np.expand_dims(np.asarray(img_resized, dtype=np.float32) / 255.0, axis=0)

    with roi_lock:
        probabilities = fruit_model.predict(image_array, verbose=0)[0]

    predicted_index = int(np.argmax(probabilities))
    confidence = float(probabilities[predicted_index])
    predicted_class = "Tidak Diketahui" if confidence < 0.40 else CLASS_NAMES[predicted_index]
    probs_raw = {CLASS_NAMES[i]: round(float(probabilities[i]), 6) for i in range(len(CLASS_NAMES))}

    return predicted_class, confidence, probs_raw


# Dipanggil oleh /predict di main.py untuk ESP32-CAM
def predict_fruit_ripeness(pil_img):
    raw_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    roi_data = compute_roi_steps(raw_bgr)
    cropped_bgr = roi_data["cropped_bgr"]

    cv2.imwrite(LATEST_CROP_IMAGE, cropped_bgr)
    predicted_class, confidence, probs_raw = _classify_cropped_bgr(cropped_bgr)
    return predicted_class, confidence, roi_data["crop_detected"], probs_raw


# =====================================================
# RUTE WEB KHUSUS PROSES ROI (/roi-lab)
# =====================================================
@roi_bp.route("/roi-lab")
def roi_lab_page():
    return render_template("roi_lab.html")


@roi_bp.route("/api/roi/process", methods=["POST"])
def api_process_roi():
    try:
        img = None
        if "file" in request.files and request.files["file"].filename != "":
            img = Image.open(request.files["file"].stream)
        elif request.form.get("source") == "latest_esp32":
            if not os.path.exists(LATEST_IMAGE):
                return jsonify({"status": "error", "error": "Belum ada gambar dari ESP32-CAM."}), 404
            img = Image.open(LATEST_IMAGE)
        else:
            return jsonify({"status": "error", "error": "Pilih gambar terlebih dahulu."}), 400

        img = ImageOps.exif_transpose(img).convert("RGB")
        raw_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        roi_data = compute_roi_steps(raw_bgr)

        # Simpan 4 tahap visualisasi ROI
        cv2.imwrite(os.path.join(ROI_DEBUG_DIR, "step1_original.jpg"), raw_bgr)
        cv2.imwrite(os.path.join(ROI_DEBUG_DIR, "step2_mask.jpg"), roi_data["mask"])

        bbox_vis = raw_bgr.copy()
        if roi_data["raw_box"] is not None:
            rx1, ry1, rx2, ry2 = roi_data["raw_box"]
            cv2.rectangle(bbox_vis, (rx1, ry1), (rx2, ry2), (0, 255, 255), 2)
        fx1, fy1, fx2, fy2 = roi_data["final_box"]
        cv2.rectangle(bbox_vis, (fx1, fy1), (fx2, fy2), (0, 255, 0), 3)
        cv2.imwrite(os.path.join(ROI_DEBUG_DIR, "step3_bbox.jpg"), bbox_vis)
        cv2.imwrite(os.path.join(ROI_DEBUG_DIR, "step4_crop.jpg"), roi_data["cropped_bgr"])

        predicted_class, confidence, probs_raw = _classify_cropped_bgr(roi_data["cropped_bgr"])
        probs_percent = {k: round(v * 100, 2) for k, v in probs_raw.items()}
        ts = int(datetime.now().timestamp())

        return jsonify({
            "status": "success",
            "data": {
                "method": roi_data["method"],
                "contour_area": roi_data["contour_area"],
                "final_box": list(roi_data["final_box"]),
                "kelas": predicted_class,
                "confidence_percent": round(confidence * 100, 2),
                "probabilities": probs_percent,
                "images": {
                    "original": f"/static/roi_debug/step1_original.jpg?t={ts}",
                    "mask": f"/static/roi_debug/step2_mask.jpg?t={ts}",
                    "bbox": f"/static/roi_debug/step3_bbox.jpg?t={ts}",
                    "crop": f"/static/roi_debug/step4_crop.jpg?t={ts}",
                },
            },
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500