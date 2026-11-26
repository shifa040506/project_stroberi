from datetime import datetime
from flask import Blueprint, request, jsonify
from firebase_admin import db

from auth_backend import device_required
from state import lock, latest_sensor, control_state

iot_bp = Blueprint("iot", __name__)

@iot_bp.route("/api/control", methods=["GET", "POST"])
def handle_control():
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

@iot_bp.get("/api/sensor")
def sensor_read():
    return jsonify(latest_sensor), 200

@iot_bp.post("/api/sensor")
@device_required
def sensor_receive():
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

        latest_sensor.update({
            "suhu": round(float(data.get("suhu", 0)), 1),
            "kelembapan_tanah": int(data.get("kelembapan_tanah", 0)),
            "kipas": str(data.get("kipas", "OFF")).upper(),
            "pompa": str(data.get("pompa", "OFF")).upper(),
            "mode": control_state["mode"],
            "waktu": waktu_sekarang,
        })

    try:
        db.reference("sensor_greenhouse/latest").set(latest_sensor)
    except Exception as fb_err:
        print("Gagal simpan sensor ke Firebase:", fb_err)

    return jsonify({"status": "success", "control": cmd_to_esp}), 200