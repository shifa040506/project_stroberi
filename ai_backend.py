import os
import time
from collections import defaultdict, deque

from flask import Blueprint, current_app, g, jsonify, request

from auth_backend import login_required


AI_LIMIT_PER_HOUR = 30
_usage = defaultdict(deque)
ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


def _allowed(user_id: int) -> bool:
    now = time.time()
    queue = _usage[user_id]
    while queue and now - queue[0] > 3600:
        queue.popleft()
    if len(queue) >= AI_LIMIT_PER_HOUR:
        return False
    queue.append(now)
    return True


def create_ai_routes(get_context):
    @ai_bp.post("/tanya")
    @login_required
    def ask():
        data = request.get_json(silent=True) or {}
        prompt = str(data.get("pesan") or "").strip()
        if not prompt:
            return jsonify({"status": "error", "error": "Pesan kosong."}), 400
        if len(prompt) > 1000:
            return jsonify({"status": "error", "error": "Pesan terlalu panjang (maks 1000 karakter)."}), 400

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"status": "error", "error": "GEMINI_API_KEY belum dikonfigurasi."}), 503
        if not _allowed(int(g.user["id"])):
            return jsonify({"status": "error", "error": "Batas penggunaan AI per jam tercapai. Coba lagi nanti."}), 429

        from google import genai
        from google.genai import types

        contents = []
        for item in (data.get("riwayat") or [])[-10:]:
            if not isinstance(item, dict):
                continue
            role = "model" if item.get("peran") == "model" else "user"
            text = str(item.get("teks") or "")[:1000]
            if text and (not contents or role != "model"):
                contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

        context = get_context()
        sensor = context.get("sensor") or {}
        diagnosis = context.get("diagnosis") or {}
        instruction = (
            "Kamu adalah asisten agronomi untuk petani stroberi hidroponik di Indonesia. "
            "Jawab dalam bahasa Indonesia, ringkas dan praktis. Bila di luar topik, tolak sopan. "
            f"Kondisi kebun: suhu {sensor.get('suhu', '-')}, kelembapan tanah {sensor.get('kelembapan_tanah', '-')}, "
            f"kipas {sensor.get('kipas', '-')}, pompa {sensor.get('pompa', '-')}, "
            f"diagnosis terakhir {diagnosis.get('penyakit_daun', '-')}. "
        )
        try:
            client = genai.Client(api_key=api_key)
            result = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    max_output_tokens=700,
                    temperature=0.4,
                ),
            )
        except Exception:
            current_app.logger.exception("Gemini gagal")
            return jsonify({"status": "error", "error": "Layanan AI sedang tidak tersedia."}), 502
        return jsonify({"status": "success", "jawaban": result.text or "Maaf, tidak ada jawaban."})

    return ai_bp
