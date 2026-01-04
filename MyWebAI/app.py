# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
import time

from flask import Flask, render_template, request, send_file

# ================== إعدادات ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOADS, exist_ok=True)

# ================== Flask ==================
app = Flask(__name__)

# ================== تنظيف تلقائي ==================
def cleanup_old_files(folder, max_age_hours=6):
    now = time.time()
    max_age = max_age_hours * 3600

    for fname in os.listdir(folder):
        path = os.path.join(folder, fname)
        if not os.path.isfile(path):
            continue

        if now - os.path.getmtime(path) > max_age:
            try:
                os.remove(path)
            except Exception:
                pass


# ================== الصفحة الرئيسية ==================
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ================== معالجة الطلب (صوت فقط) ==================
@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url", "").strip()

    if not url:
        return "❌ لم يتم إدخال رابط", 400

    # تنظيف رابط يوتيوب
    url = url.split("&")[0]

    uid = str(uuid.uuid4())
    audio_path = os.path.join(UPLOADS, f"{uid}.%(ext)s")

    # تنزيل الصوت بأعلى جودة
    subprocess.run(
        [
            "yt-dlp",
            "--no-warnings",
            "-f", "bestaudio",
            "-o", audio_path,
            url
        ],
        check=True
    )

    # إيجاد الملف الناتج (ext غير معروف مسبقًا)
    downloaded_file = None
    for f in os.listdir(UPLOADS):
        if f.startswith(uid):
            downloaded_file = f
            break

    if not downloaded_file:
        return "❌ فشل تحميل الصوت", 500

    # تنظيف ملفات قديمة
    cleanup_old_files(UPLOADS, max_age_hours=6)

    return render_template(
        "result.html",
        audio_file=f"/download/{downloaded_file}"
    )


# ================== تحميل الملفات ==================
@app.route("/download/<name>")
def download(name):
    path = os.path.join(UPLOADS, name)
    if not os.path.exists(path):
        return "❌ الملف غير موجود", 404
    return send_file(path, as_attachment=True)


# ================== تشغيل ==================
if __name__ == "__main__":
    app.run(debug=True)
