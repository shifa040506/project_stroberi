import os
import re
import mysql.connector
from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, render_template
from werkzeug.security import generate_password_hash

from auth_backend import _normal_email, _normal_phone, _password_error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

web_bp = Blueprint("web", __name__)


def _get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


@web_bp.route("/")
def home():
    return render_template("index.html")


@web_bp.route("/api/web/users", methods=["GET"])
def get_users():
    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nama, email, phone, is_verified, created_at "
            "FROM users ORDER BY id DESC"
        )
        users = cursor.fetchall()
        for u in users:
            if u.get("created_at"):
                u["created_at"] = u["created_at"].strftime("%Y-%m-%d %H:%M")
        return jsonify({"status": "success", "users": users}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@web_bp.route("/api/web/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    nama = str(data.get("nama") or "").strip()
    email = _normal_email(data.get("email"))
    password = str(data.get("password") or "")

    if not 2 <= len(nama) <= 60:
        return jsonify({"status": "error", "error": "Nama harus 2 sampai 60 karakter."}), 400

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"status": "error", "error": "Format email tidak valid."}), 400

    try:
        phone = _normal_phone(data.get("phone"))
    except ValueError as err:
        return jsonify({"status": "error", "error": str(err)}), 400

    pw_err = _password_error(password)
    if pw_err:
        return jsonify({"status": "error", "error": pw_err}), 400

    hashed_password = generate_password_hash(password)

    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
        if cursor.fetchone():
            return jsonify({"status": "error", "error": "Email atau nomor HP sudah terdaftar."}), 409

        # is_verified langsung diset 1 agar user bisa langsung login di aplikasi Flutter
        cursor.execute(
            "INSERT INTO users (nama, email, phone, password_hash, is_verified) "
            "VALUES (%s, %s, %s, %s, 1)",
            (nama, email, phone, hashed_password),
        )
        conn.commit()
        return jsonify({
            "status": "success",
            "message": f"Akun '{nama}' ({email}) berhasil dibuat dan langsung aktif untuk aplikasi Flutter.",
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@web_bp.route("/api/web/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    conn = None
    cursor = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        # Hapus riwayat OTP terkait terlebih dahulu agar tidak terblokir foreign key
        cursor.execute("DELETE FROM otp_codes WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return jsonify({"status": "success", "message": "Akun user berhasil dihapus."}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()