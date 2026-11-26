import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import Blueprint, current_app, g, jsonify, request

from auth_backend import login_required


garden_bp = Blueprint("garden", __name__, url_prefix="/api")

SENSORS = {
    "suhu_udara": {"label": "Suhu udara", "satuan": "°C"},
    "suhu_tanah": {"label": "Suhu tanah", "satuan": "°C"},
    "kelembaban_tanah": {"label": "Kelembapan tanah", "satuan": "%"},
}
PARAMETER_FIELDS = (
    "batas_kritis_bawah",
    "batas_optimal_bawah",
    "batas_optimal_atas",
    "batas_kritis_atas",
)
PROFILE_TEXT_FIELDS = (
    "alamat",
    "desa_kelurahan",
    "kecamatan",
    "kabupaten_kota",
    "provinsi",
    "kode_pos",
    "varietas",
    "kode_perangkat",
    "nomor_kontak",
    "catatan",
)
PROFILE_TEXT_LIMITS = {
    "alamat": 255,
    "desa_kelurahan": 80,
    "kecamatan": 80,
    "kabupaten_kota": 80,
    "provinsi": 80,
    "kode_pos": 5,
    "varietas": 60,
    "kode_perangkat": 40,
    "nomor_kontak": 20,
}
PROFILE_NUMBER_FIELDS = (
    "latitude",
    "longitude",
    "luas_lahan_m2",
)
PROFILE_INTEGER_FIELDS = ("ketinggian_mdpl", "jumlah_tanaman")
PROFILE_ENUMS = {
    "jenis_media": {"tanah", "cocopeat", "hidroponik", "lainnya"},
    "sistem_tanam": {"greenhouse", "lahan_terbuka"},
}


def _config(name):
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
        password=_config("DB_PASSWORD"),
        database=_config("DB_NAME"),
    )
    cursor = connection.cursor(dictionary=True)
    try:
        yield connection, cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _db_error():
    current_app.logger.exception("Permintaan data kebun gagal karena database")
    return jsonify({"status": "error", "error": "Database sedang tidak tersedia."}), 503


def _profile(cursor):
    cursor.execute(
        "SELECT * FROM profil_kebun WHERE user_id=%s ORDER BY id LIMIT 1",
        (g.user["id"],),
    )
    return cursor.fetchone()


def _serialize(row):
    return {
        key: value.isoformat() if isinstance(value, (date, datetime)) else value
        for key, value in row.items()
    }


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} harus berupa angka.")
    if not result.is_finite() or abs(result) > Decimal("9999.99"):
        raise ValueError(f"{label} harus berada antara -9999.99 dan 9999.99.")
    try:
        return result.quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"{label} harus berupa angka dengan maksimal 2 desimal.")


@garden_bp.get("/parameter")
@login_required
def parameter_list():
    try:
        with _db() as (_, cursor):
            profile = _profile(cursor)
            if profile is None:
                return jsonify({
                    "status": "error",
                    "error": "Lengkapi profil kebun sebelum mengatur parameter.",
                }), 409
            cursor.execute(
                "SELECT id, kebun_id, sensor, batas_kritis_bawah, "
                "batas_optimal_bawah, batas_optimal_atas, batas_kritis_atas, "
                "diubah_oleh, created_at, updated_at "
                "FROM parameter_sensor WHERE kebun_id=%s ORDER BY sensor",
                (profile["id"],),
            )
            parameters = cursor.fetchall()
        return jsonify({
            "status": "success",
            "parameter": [_serialize(row) for row in parameters],
            "sensor": SENSORS,
        })
    except mysql.connector.Error:
        return _db_error()


@garden_bp.put("/parameter/<sensor>")
@login_required
def parameter_update(sensor):
    if sensor not in SENSORS:
        return jsonify({"status": "error", "error": "Jenis sensor tidak dikenal."}), 404

    data = _body()
    try:
        values = [_decimal(data.get(field), field) for field in PARAMETER_FIELDS]
    except ValueError as error:
        return jsonify({"status": "error", "error": str(error)}), 400

    critical_low, optimal_low, optimal_high, critical_high = values
    if not critical_low <= optimal_low < optimal_high <= critical_high:
        return jsonify({
            "status": "error",
            "error": "Urutan batas harus kritis bawah ≤ optimal bawah < optimal atas ≤ kritis atas.",
        }), 400

    try:
        with _db() as (_, cursor):
            profile = _profile(cursor)
            if profile is None:
                return jsonify({
                    "status": "error",
                    "error": "Lengkapi profil kebun sebelum mengatur parameter.",
                }), 409
            cursor.execute(
                "SELECT id FROM parameter_sensor WHERE kebun_id=%s AND sensor=%s "
                "ORDER BY id LIMIT 1",
                (profile["id"], sensor),
            )
            existing = cursor.fetchone()
            cursor.execute("SHOW COLUMNS FROM parameter_sensor")
            columns = {row["Field"] for row in cursor.fetchall()}
            optional_values = {}
            if "status" in columns:
                optional_values["status"] = "aktif"
            if "satuan" in columns:
                optional_values["satuan"] = SENSORS[sensor]["satuan"]
            if existing:
                updates = {
                    field: value
                    for field, value in zip(PARAMETER_FIELDS, values)
                }
                updates.update(optional_values)
                updates["diubah_oleh"] = g.user["id"]
                assignments = ", ".join(f"{field}=%s" for field in updates)
                cursor.execute(
                    f"UPDATE parameter_sensor SET {assignments} WHERE id=%s",
                    (*updates.values(), existing["id"]),
                )
            else:
                fields = {
                    "kebun_id": profile["id"],
                    "sensor": sensor,
                    **{
                        field: value
                        for field, value in zip(PARAMETER_FIELDS, values)
                    },
                    **optional_values,
                    "diubah_oleh": g.user["id"],
                }
                columns_sql = ", ".join(fields)
                placeholders = ", ".join(["%s"] * len(fields))
                cursor.execute(
                    f"INSERT INTO parameter_sensor ({columns_sql}) "
                    f"VALUES ({placeholders})",
                    tuple(fields.values()),
                )
        return jsonify({"status": "success", "pesan": "Parameter sensor berhasil disimpan."})
    except mysql.connector.Error:
        return _db_error()


@garden_bp.get("/profil-kebun")
@login_required
def profile_read():
    try:
        with _db() as (_, cursor):
            profile = _profile(cursor)
        return jsonify({
            "status": "success",
            "profil": _serialize(profile) if profile else None,
        })
    except mysql.connector.Error:
        return _db_error()


@garden_bp.put("/profil-kebun")
@login_required
def profile_update():
    data = _body()
    name = str(data.get("nama_kebun") or "").strip()
    if not 2 <= len(name) <= 100:
        return jsonify({"status": "error", "error": "Nama kebun wajib diisi (2–100 karakter)."}), 400

    values = {"nama_kebun": name}
    for field in PROFILE_TEXT_FIELDS:
        value = data.get(field)
        text = str(value).strip() if value is not None else None
        limit = PROFILE_TEXT_LIMITS.get(field)
        if text is not None and limit is not None and len(text) > limit:
            return jsonify({
                "status": "error",
                "error": f"{field} maksimal {limit} karakter.",
            }), 400
        values[field] = text
    for field in PROFILE_ENUMS:
        value = data.get(field)
        if value not in (None, "") and (
            not isinstance(value, str) or value not in PROFILE_ENUMS[field]
        ):
            return jsonify({"status": "error", "error": f"Nilai {field} tidak valid."}), 400
        values[field] = value or None
    for field in PROFILE_NUMBER_FIELDS + PROFILE_INTEGER_FIELDS:
        value = data.get(field)
        if value in (None, ""):
            values[field] = None
            continue
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise InvalidOperation
            if field in PROFILE_INTEGER_FIELDS:
                upper_bound = (
                    Decimal("65535")
                    if field == "ketinggian_mdpl"
                    else Decimal("4294967295")
                )
                if (
                    number != number.to_integral_value()
                    or number < 0
                    or number > upper_bound
                ):
                    raise InvalidOperation
                values[field] = int(number)
            else:
                if field == "latitude" and not Decimal("-90") <= number <= Decimal("90"):
                    raise InvalidOperation
                if field == "longitude" and not Decimal("-180") <= number <= Decimal("180"):
                    raise InvalidOperation
                if field == "luas_lahan_m2" and not Decimal("0") <= number <= Decimal("99999999.99"):
                    raise InvalidOperation
                values[field] = number
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({"status": "error", "error": f"Nilai {field} tidak valid."}), 400
    start_date = data.get("tanggal_mulai_tanam")
    if start_date:
        try:
            values["tanggal_mulai_tanam"] = date.fromisoformat(str(start_date))
        except ValueError:
            return jsonify({"status": "error", "error": "Tanggal mulai tanam tidak valid."}), 400
    else:
        values["tanggal_mulai_tanam"] = None

    try:
        with _db() as (_, cursor):
            existing = _profile(cursor)
            if existing:
                assignments = ", ".join(f"{field}=%s" for field in values)
                cursor.execute(
                    f"UPDATE profil_kebun SET {assignments} WHERE id=%s",
                    (*values.values(), existing["id"]),
                )
            else:
                columns = ("user_id", *values.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                cursor.execute(
                    f"INSERT INTO profil_kebun ({', '.join(columns)}) "
                    f"VALUES ({placeholders})",
                    (g.user["id"], *values.values()),
                )
        return jsonify({"status": "success", "pesan": "Profil kebun berhasil disimpan."})
    except mysql.connector.Error:
        return _db_error()


@garden_bp.get("/histori")
@login_required
def history_list():
    try:
        days = int(request.args.get("hari", "1"))
    except ValueError:
        return jsonify({"status": "error", "error": "Filter hari harus 1, 2, 3, atau 7."}), 400
    if days not in {1, 2, 3, 7}:
        return jsonify({"status": "error", "error": "Filter hari harus 1, 2, 3, atau 7."}), 400

    try:
        with _db() as (_, cursor):
            profile = _profile(cursor)
            if profile is None:
                return jsonify({
                    "status": "error",
                    "error": "Lengkapi profil kebun untuk melihat histori.",
                }), 409
            cursor.execute(
                "SELECT id, kebun_id, jenis, sumber, waktu_pencatatan, foto_path, "
                "penyakit_daun, penyakit_confidence, kematangan_buah, "
                "kematangan_confidence, suhu_udara, suhu_tanah, kelembaban_tanah, "
                "created_at, updated_at FROM laporan "
                "WHERE kebun_id=%s AND waktu_pencatatan >= DATE_SUB(NOW(), INTERVAL %s DAY) "
                "ORDER BY waktu_pencatatan DESC LIMIT 500",
                (profile["id"], days),
            )
            items = cursor.fetchall()
        return jsonify({
            "status": "success",
            "hari": days,
            "laporan": [_serialize(row) for row in items],
        })
    except mysql.connector.Error:
        return _db_error()
