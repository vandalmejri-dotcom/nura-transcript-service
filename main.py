from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_video_id(url: str):
    url = url.strip()
    patterns = [
        r'youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/(?:shorts|embed|v)\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
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

    print(f"[Transcript] Fetching: {video_id}")

    ytt = YouTubeTranscriptApi()

    try:
        # Try fetching English transcript first
        try:
            fetched = ytt.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
        except Exception:
            # Fall back to any available language
            fetched = ytt.fetch(video_id)

        # Handle both old and new API response formats
        if hasattr(fetched, 'snippets'):
            items = fetched.snippets
        elif isinstance(fetched, list):
            items = fetched
        else:
            items = list(fetched)

        text = ' '.join([
            (item.text if hasattr(item, 'text') else item.get('text', ''))
            .replace('\n', ' ')
            for item in items
        ])
        text = ' '.join(text.split()).strip()

        if len(text) < 50:
            raise HTTPException(
                status_code=422,
                detail="Transcript too short to process."
            )

        print(f"[Transcript] Success! Words: {len(text.split())}")
        return {
            "success": True,
            "transcript": text,
            "wordCount": len(text.split())
        }

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        print(f"[Transcript] Error: {e}")
        if 'disabled' in err or 'no transcript' in err:
            raise HTTPException(
                status_code=422,
                detail="No transcript available for this video."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Could not fetch transcript: {str(e)}"
        )
