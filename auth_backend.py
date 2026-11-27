import hashlib
import os
import re
import secrets
import smtplib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

import jwt
import mysql.connector
from dotenv import load_dotenv
from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
OTP_TTL = timedelta(minutes=10)
OTP_RESEND_DELAY = timedelta(seconds=60)
MAX_OTP_ATTEMPTS = 5
MAX_LOGIN_ATTEMPTS = 5
LOCK_TIME = timedelta(minutes=5)


def _config(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Konfigurasi {name} belum diisi.")
    return value


@contextmanager
def _db():
    connection = mysql.connector.connect(
        host=_config("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=_config("DB_USER"),
        password=os.getenv("DB_PASSWORD", ""),  # <-- ubah baris ini
        database=_config("DB_NAME"),
    )
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        yield connection, cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        connection.close()


def _pepper() -> str:
    return _config("OTP_PEPPER")


def _normal_email(value: object) -> str:
    return str(value or "").strip().lower()


def _normal_phone(value: object) -> str:
    raw = re.sub(r"[^\d+]", "", str(value or "").strip())
    if raw.startswith("08"):
        raw = "+62" + raw[1:]
    elif raw.startswith("62"):
        raw = "+" + raw
    if not re.fullmatch(r"\+\d{10,15}", raw):
        raise ValueError("Nomor telepon tidak valid.")
    return raw


def _password_error(password: object) -> str | None:
    value = str(password or "")
    if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        return "Password minimal 8 karakter dan harus mengandung huruf serta angka."
    return None


def _otp_hash(code: str) -> str:
    return hashlib.sha256(f"{_pepper()}:{code}".encode("utf-8")).hexdigest()


def _new_otp(connection, cursor, user_id: int, purpose: str) -> str:
    cursor.execute(
        "SELECT created_at FROM otp_codes WHERE user_id=%s AND purpose=%s "
        "ORDER BY id DESC LIMIT 1",
        (user_id, purpose),
    )
    latest = cursor.fetchone()
    if latest and datetime.now() - latest["created_at"] < OTP_RESEND_DELAY:
        raise ValueError("Tunggu 60 detik sebelum meminta kode baru.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    cursor.execute(
        "INSERT INTO otp_codes (user_id, purpose, code_hash, expires_at) "
        "VALUES (%s, %s, %s, %s)",
        (user_id, purpose, _otp_hash(code), datetime.now() + OTP_TTL),
    )
    return code


def _send_otp(email: str, code: str, purpose: str) -> None:
    if os.getenv("OTP_DEV_ECHO", "0").strip() == "1":
        current_app.logger.warning("OTP %s untuk %s: %s", purpose, email, code)
        return

    host = _config("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = _config("SMTP_USER")
    password = _config("SMTP_PASS")
    sender = os.getenv("SMTP_FROM", user)
    message = EmailMessage()
    message["Subject"] = "Kode verifikasi Strawberry Care"
    message["From"] = sender
    message["To"] = email
    message.set_content(f"Kode Anda: {code}. Kode berlaku selama 10 menit.")
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(message)


def _token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["id"]),
            "ver": int(user["token_version"]),
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        _config("JWT_SECRET"),
        algorithm="HS256",
    )


def _user_data(user: dict) -> dict:
    return {
        "id": int(user["id"]),
        "nama": user["nama"],
        "email": user["email"],
        "phone": user["phone"],
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"status": "error", "error": "Belum login."}), 401
        try:
            payload = jwt.decode(
                header[7:],
                _config("JWT_SECRET"),
                algorithms=["HS256"],
            )
            user_id = int(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            return jsonify({"status": "error", "error": "Sesi tidak valid atau sudah kedaluwarsa."}), 401

        with _db() as (_, cursor):
            cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
        if user is None or int(user["token_version"]) != int(payload.get("ver", -1)):
            return jsonify({"status": "error", "error": "Sesi tidak valid atau sudah kedaluwarsa."}), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def device_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured = os.getenv("DEVICE_KEY", "").strip()
        if configured and not secrets.compare_digest(
            request.headers.get("X-Device-Key", ""),
            configured,
        ):
            return jsonify({"status": "error", "error": "Kunci perangkat tidak valid."}), 401
        return view(*args, **kwargs)

    return wrapped


def _body() -> dict:
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


@auth_bp.post("/register")
def register():
    data = _body()
    name = str(data.get("nama") or "").strip()
    email = _normal_email(data.get("email"))
    try:
        phone = _normal_phone(data.get("phone"))
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 400
    password_error = _password_error(data.get("password"))
    if not 2 <= len(name) <= 60 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"status": "error", "error": "Nama atau email tidak valid."}), 400
    if password_error:
        return jsonify({"status": "error", "error": password_error}), 400

    try:
        with _db() as (connection, cursor):
            cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
            if cursor.fetchone():
                return jsonify({"status": "error", "error": "Email atau nomor telepon sudah terdaftar."}), 409
            cursor.execute(
                "INSERT INTO users (nama, email, phone, password_hash) VALUES (%s, %s, %s, %s)",
                (name, email, phone, generate_password_hash(str(data["password"]))),
            )
            user_id = cursor.lastrowid
            code = _new_otp(connection, cursor, user_id, "register")
        _send_otp(email, code, "register")
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 429
    except smtplib.SMTPException:
        current_app.logger.exception("Pengiriman OTP registrasi gagal")
        return jsonify({"status": "error", "error": "Gagal mengirim email OTP."}), 502
    except mysql.connector.Error:
        current_app.logger.exception("Database registrasi gagal")
        return jsonify({"status": "error", "error": "Database sedang tidak tersedia."}), 503
    return jsonify({"status": "success", "pesan": "Kode verifikasi telah dikirim."}), 201


def _verify_code(email: str, code: str, purpose: str):
    with _db() as (connection, cursor):
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user is None:
            return None, "Kode salah atau kedaluwarsa."
        cursor.execute(
            "SELECT * FROM otp_codes WHERE user_id=%s AND purpose=%s AND used_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (user["id"], purpose),
        )
        otp = cursor.fetchone()
        if otp is None or otp["expires_at"] < datetime.now():
            return None, "Kode kedaluwarsa."
        if int(otp["attempts"]) >= MAX_OTP_ATTEMPTS:
            return None, "Terlalu banyak percobaan."
        if not secrets.compare_digest(otp["code_hash"], _otp_hash(code)):
            cursor.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=%s", (otp["id"],))
            return None, "Kode salah."
        cursor.execute("UPDATE otp_codes SET used_at=NOW() WHERE id=%s", (otp["id"],))
        return user, None


@auth_bp.post("/verifikasi")
def verify():
    data = _body()
    user, error = _verify_code(_normal_email(data.get("email")), str(data.get("kode") or ""), "register")
    if error:
        return jsonify({"status": "error", "error": error}), 400
    with _db() as (_, cursor):
        cursor.execute("UPDATE users SET is_verified=1 WHERE id=%s", (user["id"],))
    user["is_verified"] = 1
    return jsonify({"status": "success", "token": _token(user), "user": _user_data(user)})


@auth_bp.post("/kirim-ulang")
def resend():
    email = _normal_email(_body().get("email"))
    if not email:
        return jsonify({"status": "success", "pesan": "Jika akun tersedia, kode telah dikirim."})
    try:
        with _db() as (connection, cursor):
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()
            if user is None or user["is_verified"]:
                return jsonify({"status": "success", "pesan": "Jika akun tersedia, kode telah dikirim."})
            code = _new_otp(connection, cursor, user["id"], "register")
        _send_otp(email, code, "register")
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 429
    except smtplib.SMTPException:
        current_app.logger.exception("Pengiriman OTP ulang gagal")
        return jsonify({"status": "error", "error": "Gagal mengirim email OTP."}), 502
    return jsonify({"status": "success", "pesan": "Jika akun tersedia, kode telah dikirim."})


@auth_bp.post("/login")
def login():
    data = _body()
    email = _normal_email(data.get("email"))
    now = datetime.now()

    with _db() as (_, cursor):
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

    if user and user["terkunci_sampai"] and user["terkunci_sampai"] > now:
        return jsonify({"status": "error", "error": "Akun dikunci sementara. Coba lagi nanti."}), 429

    if user is None or not check_password_hash(user["password_hash"], str(data.get("password") or "")):
        if user:
            # Reset hitungan gagal jika masa kunci sebelumnya sudah lewat
            prev_fails = 0 if (user["terkunci_sampai"] and user["terkunci_sampai"] <= now) else int(user["gagal_login"])
            new_fails = prev_fails + 1
            lock_until = (now + LOCK_TIME) if new_fails >= MAX_LOGIN_ATTEMPTS else None
            with _db() as (_, cursor):
                cursor.execute(
                    "UPDATE users SET gagal_login=%s, terkunci_sampai=%s WHERE id=%s",
                    (new_fails, lock_until, user["id"]),
                )
        return jsonify({"status": "error", "error": "Email atau password salah."}), 401

    if not user["is_verified"]:
        return jsonify({"status": "error", "kode_error": "belum_verifikasi", "error": "Email belum diverifikasi."}), 403

    with _db() as (_, cursor):
        cursor.execute("UPDATE users SET gagal_login=0, terkunci_sampai=NULL WHERE id=%s", (user["id"],))
    return jsonify({"status": "success", "token": _token(user), "user": _user_data(user)})


@auth_bp.post("/lupa")
def forgot():
    try:
        phone = _normal_phone(_body().get("phone"))
    except ValueError:
        return jsonify({"status": "success", "pesan": "Jika nomor terdaftar, kode reset telah dikirim."})

    try:
        with _db() as (connection, cursor):
            cursor.execute("SELECT * FROM users WHERE phone=%s", (phone,))
            user = cursor.fetchone()
            if user:
                code = _new_otp(connection, cursor, user["id"], "reset")
                email = user["email"]
            else:
                code = email = None
        if code and email:
            _send_otp(email, code, "reset")
    except ValueError:
        return jsonify({"status": "error", "error": "Tunggu 60 detik sebelum meminta kode baru."}), 429
    except smtplib.SMTPException:
        current_app.logger.exception("Pengiriman OTP reset gagal")
        return jsonify({"status": "error", "error": "Gagal mengirim email OTP."}), 502
    return jsonify({"status": "success", "pesan": "Jika nomor terdaftar, kode reset telah dikirim."})


@auth_bp.post("/reset")
def reset():
    data = _body()
    try:
        phone = _normal_phone(data.get("phone"))
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 400
    password_error = _password_error(data.get("password_baru"))
    if password_error:
        return jsonify({"status": "error", "error": password_error}), 400
    with _db() as (_, cursor):
        cursor.execute("SELECT * FROM users WHERE phone=%s", (phone,))
        user = cursor.fetchone()
    if user is None:
        return jsonify({"status": "error", "error": "Kode salah atau kedaluwarsa."}), 400
    verified, error = _verify_code(user["email"], str(data.get("kode") or ""), "reset")
    if error:
        return jsonify({"status": "error", "error": error}), 400
    with _db() as (_, cursor):
        cursor.execute(
            "UPDATE users SET password_hash=%s, token_version=token_version+1, gagal_login=0, terkunci_sampai=NULL WHERE id=%s",
            (generate_password_hash(str(data["password_baru"])), verified["id"]),
        )
    return jsonify({"status": "success", "pesan": "Password berhasil diubah."})


@auth_bp.get("/me")
@login_required
def me():
    return jsonify({"status": "success", "user": _user_data(g.user)})


@auth_bp.post("/keluar-semua")
@login_required
def logout_all():
    with _db() as (_, cursor):
        cursor.execute("UPDATE users SET token_version=token_version+1 WHERE id=%s", (g.user["id"],))
    return jsonify({"status": "success"})