#!/usr/bin/env python3
"""
Flask web app — downloads a Douyin/TikTok video and transcribes it via Claude API.

Run:
    ANTHROPIC_API_KEY=sk-ant-... python3 app.py
Then open: http://localhost:5000
"""

import re
import os
import base64
import tempfile
from flask import Flask, request, jsonify, render_template_string

import yt_dlp
import anthropic

app = Flask(__name__)


def extract_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    if not match:
        raise ValueError("No URL found in input.")
    return match.group(0).rstrip("…")


def download_audio(url: str, out_dir: str) -> str:
    """Download best audio from URL, convert to mp3. Returns file path."""
    out_template = os.path.join(out_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    mp3_path = os.path.join(out_dir, "audio.mp3")
    if not os.path.exists(mp3_path):
        for fname in sorted(os.listdir(out_dir)):
            if fname.startswith("audio."):
                mp3_path = os.path.join(out_dir, fname)
                break
    return mp3_path


def transcribe_with_claude(audio_path: str) -> str:
    """Send audio to Claude API for transcription."""
    ext = os.path.splitext(audio_path)[1].lower()
    media_type_map = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    media_type = media_type_map.get(ext, "audio/mpeg")

    with open(audio_path, "rb") as f:
        audio_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Please transcribe this audio exactly as spoken. "
                            "Output only the transcription text — no commentary, "
                            "no timestamps, no labels."
                        ),
                    },
                    {
                        "type": "audio",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": audio_b64,
                        },
                    },
                ],
            }
        ],
    )
    return response.content[0].text


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Douyin Transcriber</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f0f0f; color: #eee;
           min-height: 100vh; display: flex; flex-direction: column;
           align-items: center; padding: 40px 16px; }
    h1 { font-size: 1.6rem; margin-bottom: 8px; }
    p.sub { color: #888; font-size: 0.9rem; margin-bottom: 32px; }
    .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
            padding: 28px; width: 100%; max-width: 640px; }
    textarea { width: 100%; height: 90px; background: #111; border: 1px solid #333;
               border-radius: 8px; color: #eee; font-size: 0.95rem; padding: 12px;
               resize: vertical; outline: none; }
    textarea:focus { border-color: #555; }
    button.primary { margin-top: 14px; width: 100%; padding: 12px; background: #e04;
                     border: none; border-radius: 8px; color: #fff; font-size: 1rem;
                     font-weight: 600; cursor: pointer; transition: background 0.2s; }
    button.primary:hover { background: #c03; }
    button.primary:disabled { background: #555; cursor: not-allowed; }
    #status { margin-top: 18px; font-size: 0.88rem; color: #aaa; min-height: 20px; }
    #result { margin-top: 18px; background: #111; border: 1px solid #2a2a2a;
              border-radius: 8px; padding: 16px; font-size: 0.95rem; line-height: 1.7;
              white-space: pre-wrap; display: none; }
    .copy-btn { margin-top: 10px; background: #222; border: 1px solid #333; color: #ccc;
                padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
    .copy-btn:hover { background: #333; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #555;
               border-top-color: #aaa; border-radius: 50%; animation: spin 0.8s linear infinite;
               margin-right: 6px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <h1>Douyin Transcriber</h1>
  <p class="sub">Paste a Douyin/TikTok URL or full share text — powered by Claude AI</p>
  <div class="card">
    <textarea id="input" placeholder="https://v.douyin.com/...&#10;or paste full share text with embedded URL"></textarea>
    <button class="primary" id="btn" onclick="transcribe()">Transcribe</button>
    <div id="status"></div>
    <div id="result"></div>
    <button class="copy-btn" id="copy-btn" style="display:none" onclick="copyText()">Copy transcript</button>
  </div>

  <script>
    async function transcribe() {
      const input = document.getElementById('input').value.trim();
      if (!input) return;
      const btn = document.getElementById('btn');
      const status = document.getElementById('status');
      const result = document.getElementById('result');
      const copyBtn = document.getElementById('copy-btn');

      btn.disabled = true;
      result.style.display = 'none';
      copyBtn.style.display = 'none';
      status.innerHTML = '<span class="spinner"></span>Downloading and transcribing via Claude… may take a minute.';

      try {
        const res = await fetch('/transcribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input }),
        });
        const data = await res.json();
        if (data.error) {
          status.textContent = 'Error: ' + data.error;
        } else {
          status.textContent = 'Done!';
          result.textContent = data.transcript;
          result.style.display = 'block';
          copyBtn.style.display = 'inline-block';
        }
      } catch (e) {
        status.textContent = 'Request failed: ' + e.message;
      } finally {
        btn.disabled = false;
      }
    }

    function copyText() {
      const text = document.getElementById('result').textContent;
      navigator.clipboard.writeText(text).then(() => {
        document.getElementById('copy-btn').textContent = 'Copied!';
        setTimeout(() => document.getElementById('copy-btn').textContent = 'Copy transcript', 2000);
      });
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    data = request.get_json(force=True)
    raw = data.get("input", "").strip()
    if not raw:
        return jsonify({"error": "No input provided."}), 400

    try:
        url = extract_url(raw)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY is not set. Set it before starting the server."}), 500

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = download_audio(url, tmpdir)
            transcript = transcribe_with_claude(audio_path)
        return jsonify({"transcript": transcript, "url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY is not set. Transcription will fail.")
        print("Run with: ANTHROPIC_API_KEY=sk-ant-... python3 app.py")
    app.run(host="0.0.0.0", port=5000, debug=False)
