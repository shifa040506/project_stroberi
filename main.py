import os
from dotenv import load_dotenv
import mysql.connector

import firebase_admin
from firebase_admin import credentials
from flask import Flask
from flask_cors import CORS

from state import BASE_DIR, latest_sensor, latest_result
from auth_backend import auth_bp
from ai_backend import create_ai_routes
from roi_backend import roi_bp
from web_backend import web_bp
from iot_sensor_backend import iot_bp
from camera_backend import camera_bp
from leaf_mobile_backend import leaf_mobile_bp

# =====================================================
# INISIALISASI FLASK, ENV, MYSQL & FIREBASE
# =====================================================
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("JWT_SECRET", "strawberry_greenhouse_secret_2026")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
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
# REGISTRASI SEMUA BLUEPRINT
# =====================================================
app.register_blueprint(auth_bp)
app.register_blueprint(
    create_ai_routes(
        lambda: {"sensor": latest_sensor, "diagnosis": latest_result}
    )
)
app.register_blueprint(roi_bp)
app.register_blueprint(web_bp)
app.register_blueprint(iot_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(leaf_mobile_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)