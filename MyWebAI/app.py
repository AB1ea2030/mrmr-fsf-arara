# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
import time
from xml.sax.saxutils import escape as html_escape

from flask import Flask, render_template, request, send_file

import whisper

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

import arabic_reshaper
from bidi.algorithm import get_display


# ================== إعدادات ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE_DIR, "uploads")
OUTPUTS = os.path.join(BASE_DIR, "outputs")
FONTS = os.path.join(BASE_DIR, "fonts")

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

# ================== الخط ==================
pdfmetrics.registerFont(
    TTFont("Cairo", os.path.join(FONTS, "Cairo-Regular.ttf"))
)

# ================== Flask ==================
app = Flask(__name__)

# تحميل Whisper مرة واحدة
model = whisper.load_model("tiny")


# ================== أدوات عربية ==================
def fix_arabic(text: str) -> str:
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def has_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in text)


# ================== تقسيم ذكي للنص ==================
def smart_paragraphs(text: str):
    separators = ["\n", "؟", ".", "،", "!"]
    for sep in separators:
        text = text.replace(sep, sep + "\n")

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    paragraphs = []
    buffer = ""

    for line in lines:
        buffer += " " + line
        if len(buffer) > 120:
            paragraphs.append(buffer.strip())
            buffer = ""

    if buffer:
        paragraphs.append(buffer.strip())

    return paragraphs


# ================== صوت ==================
def audio_to_wav(input_audio, wav_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_audio, "-ar", "16000", "-ac", "1", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )


# ================== خطة B: تقسيم صوت ==================
def split_audio_ffmpeg(input_audio, out_dir, chunk_seconds=600):
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "chunk_%03d.wav")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", input_audio,
            "-f", "segment",
            "-segment_time", str(chunk_seconds),
            "-ar", "16000",
            "-ac", "1",
            pattern
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )


def transcribe_chunks(chunks_dir):
    texts = []

    for fname in sorted(os.listdir(chunks_dir)):
        if not fname.endswith(".wav"):
            continue

        path = os.path.join(chunks_dir, fname)
        result = model.transcribe(path)
        texts.append(result["text"])

        os.remove(path)

    return "\n".join(texts)


# ================== تنظيف تلقائي ==================
def cleanup_old_files(folder, max_age_hours):
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


# ================== PDF ==================
def create_pdf(text: str, pdf_path: str):
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Arabic",
            fontName="Cairo",
            fontSize=12,
            leading=18,
            alignment=2,
            spaceAfter=8,
            spaceBefore=4
        )
    )

    story = []
    paragraphs = smart_paragraphs(text)

    for para in paragraphs:
        para = html_escape(para)
        if has_arabic(para):
            para = fix_arabic(para)

        story.append(Paragraph(para, styles["Arabic"]))
        story.append(Spacer(1, 10))

    doc.build(story)


# ================== الصفحة الرئيسية ==================
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ================== معالجة الطلب ==================
@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url", "")
    mode = request.form.get("mode", "text")

    if url:
        url = url.split("&")[0]

    uid = str(uuid.uuid4())
    audio_path = os.path.join(UPLOADS, f"{uid}.webm")

    subprocess.run(
        [
            "python", "-m", "yt_dlp",
            "--no-warnings",
            "-f", "bestaudio",
            "-o", audio_path,
            url
        ],
        check=True
    )

    result_text = ""
    pdf_link = None
    audio_link = None

    if mode in ("text", "both"):
        wav_path = os.path.join(UPLOADS, f"{uid}.wav")
        audio_to_wav(audio_path, wav_path)

        try:
            # ===== خطة A =====
            result_detect = model.transcribe(wav_path)
            lang = result_detect.get("language", "en")

            result = model.transcribe(wav_path, language=lang)
            result_text = result["text"]

        except Exception:
            # ===== خطة B =====
            chunks_dir = os.path.join(UPLOADS, f"{uid}_chunks")
            split_audio_ffmpeg(wav_path, chunks_dir, chunk_seconds=600)
            result_text = transcribe_chunks(chunks_dir)
            os.rmdir(chunks_dir)

        pdf_path = os.path.join(OUTPUTS, f"{uid}.pdf")
        create_pdf(result_text, pdf_path)
        pdf_link = f"/download/{uid}.pdf"

        if os.path.exists(wav_path):
            os.remove(wav_path)

    if mode in ("audio", "both"):
        audio_link = f"/download/{uid}.webm"

    if mode == "text" and os.path.exists(audio_path):
        os.remove(audio_path)

    # ✅ تنظيف تلقائي
    cleanup_old_files(UPLOADS, max_age_hours=6)
    cleanup_old_files(OUTPUTS, max_age_hours=24)

    return render_template(
        "result.html",
        text=result_text,
        pdf_file=pdf_link,
        audio_file=audio_link
    )


# ================== تحميل الملفات ==================
@app.route("/download/<name>")
def download(name):
    path = os.path.join(UPLOADS, name)
    if not os.path.exists(path):
        path = os.path.join(OUTPUTS, name)
    return send_file(path, as_attachment=True)


# ================== تشغيل ==================
if __name__ == "__main__":
    app.run(debug=True)
