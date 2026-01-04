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


# ================== yt-dlp مع Retry ذكي ==================
def download_audio_with_retry(url, output_template):
    formats = [
        "bestaudio",
        "bestaudio/best",
        "best"
    ]

    for fmt in formats:
        try:
            subprocess.run(
                [
                    "yt-dlp",

                    # تقليل الاشتباه
                    "--user-agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",

                    "--referer", "https://www.youtube.com/",
                    "--no-check-certificate",

                    # سلوك بشري
                    "--sleep-interval", "1",
                    "--max-sleep-interval", "3",

                    # إعادة المحاولة
                    "--retries", "5",
                    "--fragment-retries", "5",

                    # الصيغة
                    "-f", fmt,

                    # الإخراج
                    "-o", output_template,

                    url
                ],
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            time.sleep(2)  # انتظار قبل المحاولة التالية

    return False


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
    audio_path_template = os.path.join(UPLOADS, f"{uid}.%(ext)s")

    success = download_audio_with_retry(url, audio_path_template)

    if not success:
        return (
            "⚠️ تعذر تحميل هذا الفيديو. "
            "قد يكون محميًا ويتطلب تسجيل دخول يوتيوب.",
            500
        )

    # إيجاد الملف الناتج
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
