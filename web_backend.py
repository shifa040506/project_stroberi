import os
import re
import mysql.connector
from dotenv import load_dotenv
from flask import (
    Blueprint,
    current_app,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash

from auth_backend import _db, _normal_email, _normal_phone, _password_error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

web_bp = Blueprint("web", __name__)


def _is_admin_logged_in() -> bool:
    return bool(session.get("admin_logged_in"))


@web_bp.before_app_request
def protect_admin_pages():
    path = request.path
    # Halaman web & endpoint manajemen user wajib login admin
    protected_pages = {"/", "/roi-lab"}
    if path in protected_pages and not _is_admin_logged_in():
        return redirect(url_for("web.login_page"))

    if path.startswith("/api/web/") and not _is_admin_logged_in():
        return jsonify({"status": "error", "error": "Sesi admin berakhir. Silakan login kembali."}), 401


@web_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if _is_admin_logged_in():
        return redirect(url_for("web.home"))

    error = None
    username_input = ""

    if request.method == "POST":
        username_input = str(request.form.get("username") or "").strip()
        password_input = str(request.form.get("password") or "")

        try:
            with _db() as (_, cursor):
                cursor.execute(
                    "SELECT nama, password_hash, is_verified FROM users "
                    "WHERE nama=%s AND role=%s",
                    (username_input, "admin"),
                )
                admin_users = cursor.fetchall()
        except mysql.connector.Error:
            current_app.logger.exception("Database login admin gagal")
            error = "Database tidak tersedia. Silakan coba lagi."
        else:
            admin_user = next(
                (
                    user
                    for user in admin_users
                    if user["is_verified"]
                    and check_password_hash(user["password_hash"], password_input)
                ),
                None,
            )
            if admin_user:
                session.clear()
                session["admin_logged_in"] = True
                session["admin_username"] = admin_user["nama"]
                return redirect(url_for("web.home"))

            error = "Username/password admin salah atau akun belum diverifikasi."

    return render_template("login.html", error=error, username=username_input)


@web_bp.route("/logout", methods=["GET", "POST"])
def logout_page():
    session.clear()
    return redirect(url_for("web.login_page"))


@web_bp.route("/")
def home():
    return render_template("index.html")


@web_bp.route("/api/web/users", methods=["GET"])
def get_users():
    try:
        with _db() as (_, cursor):
            cursor.execute(
                "SELECT id, nama, email, phone, is_verified, created_at "
                "FROM users ORDER BY id DESC"
            )
            users = cursor.fetchall()

        for u in users:
            created = u.get("created_at")
            if created and hasattr(created, "strftime"):
                u["created_at"] = created.strftime("%Y-%m-%d %H:%M")

        return jsonify({"status": "success", "users": users}), 200
    except mysql.connector.Error:
        return jsonify({"status": "error", "error": "Gagal mengambil data user dari database."}), 503


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

    try:
        with _db() as (_, cursor):
            cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
            if cursor.fetchone():
                return jsonify({"status": "error", "error": "Email atau nomor HP sudah terdaftar."}), 409

            cursor.execute(
                "INSERT INTO users (nama, email, phone, role, password_hash, is_verified) "
                "VALUES (%s, %s, %s, %s, %s, 1)",
                (nama, email, phone, "user", hashed_password),
            )

        return jsonify({
            "status": "success",
            "message": f"Akun '{nama}' ({email}) berhasil dibuat dan langsung aktif untuk aplikasi Flutter.",
        }), 201
    except mysql.connector.IntegrityError:
        return jsonify({"status": "error", "error": "Email atau nomor HP sudah terdaftar."}), 409
    except mysql.connector.Error:
        return jsonify({"status": "error", "error": "Database sedang tidak tersedia."}), 503


@web_bp.route("/api/web/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        with _db() as (_, cursor):
            cursor.execute("DELETE FROM otp_codes WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            if cursor.rowcount == 0:
                return jsonify({"status": "error", "error": "Akun user tidak ditemukan."}), 404

        return jsonify({"status": "success", "message": "Akun user berhasil dihapus."}), 200
    except mysql.connector.Error:
        return jsonify({"status": "error", "error": "Gagal menghapus akun user."}), 503