from fastapi import FastAPI, HTTPException
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import GenericProxyConfig
import re
import os

app = FastAPI()

def extract_video_id(url: str):
    # Strip everything after & or ? except v= parameter
    # Clean the URL first
    url = url.strip()
    
    patterns = [
        r'youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
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

    print(f"[Transcript] URL received: {url}")
    print(f"[Transcript] Video ID extracted: {video_id}")

    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # List of languages to try in order
    language_attempts = [
        ['en'],
        ['en-US'],
        ['en-GB'],
        None  # None means try any available language
    ]

    last_error = None

    for languages in language_attempts:
        print(f"[Transcript] Attempting languages: {languages}")
        try:
            if languages:
                transcript_list = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=languages,
                    cookies=os.environ.get("YOUTUBE_COOKIES_PATH")
                )
            else:
                # Get any available transcript
                transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = next(iter(transcripts))
                transcript_list = transcript.fetch()

            text = ' '.join([
                item['text'].replace('\n', ' ')
                for item in transcript_list
                if item.get('text')
            ])
            text = ' '.join(text.split()).strip()

            if len(text) < 50:
                raise Exception("Transcript too short")

            return {
                "success": True,
                "transcript": text,
                "wordCount": len(text.split())
            }

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            raise HTTPException(
                status_code=422,
                detail="No transcript available for this video. Captions may be disabled."
            )
        except Exception as e:
            print(f"[Transcript] Error: {str(e)}")
            last_error = str(e)
            continue

    # All attempts failed
    error_msg = str(last_error) if last_error else "Unknown error"
    if "blocked" in error_msg.lower() or "429" in error_msg or "IP" in error_msg:
        raise HTTPException(
            status_code=503,
            detail="YouTube is temporarily blocking requests. Please try again in 60 seconds."
        )
    raise HTTPException(
        status_code=500,
        detail=f"Could not fetch transcript: {error_msg}"
    )
