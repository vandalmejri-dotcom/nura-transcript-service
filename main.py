"""
Nura Transcript Service — powered by yt-dlp
Deployed on Render. Called by the Nura AI Next.js app on Vercel.

yt-dlp is the most reliable YouTube data extractor available and handles
YouTube's constantly evolving anti-bot measures automatically.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import re
import json
import subprocess
import sys

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_video_id(url: str):
    pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def extract_text_from_json3(data: dict) -> str:
    """Extract plain text from YouTube's json3 subtitle format."""
    events = data.get("events", [])
    parts = []
    for event in events:
        segs = event.get("segs")
        if segs:
            parts.append("".join(s.get("utf8", "") for s in segs))
    return " ".join(parts).replace("\n", " ").strip()


def extract_text_from_vtt(vtt: str) -> str:
    """Extract plain text from WebVTT subtitle format."""
    lines = vtt.split("\n")
    text_parts = []
    for line in lines:
        line = line.strip()
        if (not line or "-->" in line or line.isdigit() or
                line.startswith("WEBVTT") or line.startswith("Kind:") or
                line.startswith("Language:") or line.startswith("NOTE") or
                line.startswith("STYLE")):
            continue
        # Strip inline tags like <c>, <00:00:01.000>
        cleaned = re.sub(r'<[^>]+>', '', line).strip()
        if cleaned:
            text_parts.append(cleaned)
    return " ".join(text_parts)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcript")
def get_transcript(body: dict):
    url = body.get("url", "")
    video_id = extract_video_id(url)

    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    print(f"[Transcript] Extracting for video: {video_id}")

    # ─── Use yt-dlp to get subtitle URLs ───────────────────────────────────────
    # yt-dlp is installed as a Python package (see requirements.txt)
    # We run it as a subprocess to get JSON metadata containing subtitle URLs.
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--skip-download",
                "--dump-json",
                "--no-warnings",
                "--no-check-certificates",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr = result.stderr or ""
            if "Video unavailable" in stderr or "Private video" in stderr:
                raise HTTPException(status_code=404, detail="This video is unavailable or private.")
            if "Sign in" in stderr or "age" in stderr.lower():
                raise HTTPException(status_code=403, detail="This video requires sign-in (age-restricted).")
            raise Exception(f"yt-dlp failed: {stderr[:300]}")

        info = json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Transcript extraction timed out. Please try again.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Transcript] yt-dlp error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {str(e)}")

    title = info.get("title", "YouTube Video")
    print(f"[Transcript] Video: \"{title}\"")

    # ─── Pick best subtitle track ───────────────────────────────────────────────
    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})

    def pick_best(subs_dict):
        """Pick English or first available language track."""
        if not subs_dict:
            return None, None
        if "en" in subs_dict:
            return "en", subs_dict["en"]
        en_key = next((k for k in subs_dict if k.startswith("en")), None)
        if en_key:
            return en_key, subs_dict[en_key]
        first_key = next(iter(subs_dict))
        return first_key, subs_dict[first_key]

    lang, tracks = pick_best(subtitles)
    is_auto = False
    if not tracks:
        lang, tracks = pick_best(auto_captions)
        is_auto = True

    if not tracks:
        raise HTTPException(status_code=422, detail="No captions or subtitles available for this video.")

    print(f"[Transcript] Using {'auto' if is_auto else 'manual'} subtitles in: {lang}")

    # ─── Fetch subtitle text ────────────────────────────────────────────────────
    import urllib.request

    format_priority = ["json3", "vtt", "srt", "srv3", "ttml"]
    transcript_text = None

    for fmt in format_priority:
        track = next((t for t in tracks if t.get("ext") == fmt), None)
        if not track or not track.get("url"):
            continue
        try:
            with urllib.request.urlopen(track["url"], timeout=10) as resp:
                body_bytes = resp.read()
                body_str = body_bytes.decode("utf-8", errors="replace")

            if len(body_str) < 10:
                continue

            if fmt == "json3":
                data = json.loads(body_str)
                text = extract_text_from_json3(data)
            elif fmt in ("vtt", "srt"):
                text = extract_text_from_vtt(body_str)
            else:
                # srv3 / ttml — strip XML tags
                text = re.sub(r'<[^>]+>', ' ', body_str)
                text = re.sub(r'\s+', ' ', text).strip()

            if text and len(text) > 50:
                transcript_text = text
                print(f"[Transcript] Extracted {len(text)} chars via {fmt}")
                break

        except Exception as e:
            print(f"[Transcript] Failed to fetch {fmt}: {e}")
            continue

    if not transcript_text:
        raise HTTPException(status_code=422, detail="Could not extract text from any available subtitle format.")

    word_count = len(transcript_text.split())
    print(f"[Transcript] ✓ Done — \"{title}\" — {len(transcript_text)} chars, {word_count} words")

    return {
        "success": True,
        "transcript": transcript_text,
        "title": title,
        "wordCount": word_count,
        "language": lang,
    }
