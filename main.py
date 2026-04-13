from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_video_id(url: str):
    url = url.strip()
    short_match = re.search(r'youtu\.be\/([a-zA-Z0-9_-]{11})', url)
    if short_match:
        return short_match.group(1)
    watch_match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url)
    if watch_match:
        return watch_match.group(1)
    other_match = re.search(
        r'youtube\.com\/(?:shorts|embed|v)\/([a-zA-Z0-9_-]{11})', url
    )
    if other_match:
        return other_match.group(1)
    return None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/transcript")
def get_transcript(body: dict):
    url = body.get("url", "")
    video_id = extract_video_id(url)

    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    print(f"[Transcript] Fetching video_id: {video_id}")

    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=['en', 'en-US', 'en-GB']
        )
    except Exception as e1:
        print(f"[Transcript] English failed: {e1}, trying any language...")
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        except TranscriptsDisabled:
            raise HTTPException(
                status_code=422,
                detail="Transcripts are disabled for this video."
            )
        except NoTranscriptFound:
            raise HTTPException(
                status_code=422,
                detail="No transcript found for this video."
            )
        except Exception as e2:
            print(f"[Transcript] All attempts failed: {e2}")
            raise HTTPException(
                status_code=500,
                detail=f"Could not fetch transcript: {str(e2)}"
            )

    text = ' '.join([
        item['text'].replace('\n', ' ')
        for item in transcript_list
        if item.get('text')
    ])
    text = ' '.join(text.split()).strip()

    if len(text) < 50:
        raise HTTPException(
            status_code=422,
            detail="Transcript is too short to process."
        )

    print(f"[Transcript] Success! Words: {len(text.split())}")
    return {
        "success": True,
        "transcript": text,
        "wordCount": len(text.split())
    }
