#!/usr/bin/env python3
"""
douyin_transcript.py - Download a Douyin/TikTok video and transcribe its audio using Whisper.

Usage:
    python3 douyin_transcript.py "<url_or_share_text>"

Examples:
    python3 douyin_transcript.py "https://v.douyin.com/uqiN-Pfxji0/"
    python3 douyin_transcript.py "2.87 复制打开抖音... https://v.douyin.com/uqiN-Pfxji0/ ..."
"""

import re
import sys
import os
import tempfile
import subprocess

import yt_dlp
import whisper


def extract_url(text: str) -> str:
    """Extract the first URL from a block of share text."""
    match = re.search(r"https?://\S+", text)
    if not match:
        raise ValueError(f"No URL found in input: {text!r}")
    return match.group(0).rstrip("…")


def download_audio(url: str, out_dir: str) -> str:
    """Download video from URL and extract audio as wav. Returns path to wav file."""
    out_template = os.path.join(out_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
        "quiet": False,
        "no_warnings": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    wav_path = os.path.join(out_dir, "audio.wav")
    if not os.path.exists(wav_path):
        # yt-dlp may have kept a different extension; find it
        for fname in os.listdir(out_dir):
            if fname.startswith("audio."):
                wav_path = os.path.join(out_dir, fname)
                break
    return wav_path


def transcribe(audio_path: str, model_name: str = "base") -> str:
    """Transcribe audio file with Whisper. Returns the transcript text."""
    print(f"Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)
    print(f"Transcribing {audio_path} ...")
    result = model.transcribe(audio_path)
    return result["text"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    raw_input = sys.argv[1]
    url = extract_url(raw_input)
    print(f"URL: {url}")

    with tempfile.TemporaryDirectory() as tmpdir:
        print("Downloading audio...")
        audio_path = download_audio(url, tmpdir)
        print(f"Audio saved to: {audio_path}")

        transcript = transcribe(audio_path)

    print("\n=== TRANSCRIPT ===")
    print(transcript)
    print("==================")
    return transcript


if __name__ == "__main__":
    main()
