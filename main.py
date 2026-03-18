from fastapi import FastAPI, HTTPException
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
import re

app = FastAPI()

def extract_video_id(url: str):
    pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/transcript")
def get_transcript(body: dict):
    url = body.get("url", "")
    video_id = extract_video_id(url)
    
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        
    try:
        # NEW SYNTAX: Initialize the object first
        ytt_api = YouTubeTranscriptApi()
        
        try:
            # Try English first
            transcript_list = ytt_api.fetch(video_id, languages=['en']).to_raw_data()
        except Exception:
            # Fallback to default language
            transcript_list = ytt_api.fetch(video_id).to_raw_data()
            
        text = ' '.join([item['text'] for item in transcript_list])
        text = ' '.join(text.split())
        
        return {
            "success": True,
            "transcript": text,
            "wordCount": len(text.split())
        }
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
