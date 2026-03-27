from fastapi import FastAPI, HTTPException
from youtube_transcript_api import YouTubeTranscriptApi
import re
import requests

app = FastAPI()

def extract_video_id(url: str):
    pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def clean_vtt(vtt_content: str) -> str:
    """Parses and cleans raw VTT/XML subtitle files into plain text."""
    lines = vtt_content.split('\n')
    segments = []
    last_text = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or '-->' in line or line.isdigit() or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        cleaned = re.sub(r'<[^>]+>', '', line).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ').strip()
        if cleaned and cleaned != last_text:
            segments.append(cleaned)
            last_text = cleaned
    return ' '.join(segments)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/transcript")
def get_transcript(body: dict):
    url = body.get("url", "")
    video_id = extract_video_id(url)
    
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        
    # ATTEMPT 1: Direct extraction
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['en'])
        except Exception:
            transcript = next(iter(transcript_list))
            
        fetched_data = transcript.fetch()
        text = ' '.join([item['text'] for item in fetched_data])
        text = ' '.join(text.split())
        
        return {"success": True, "transcript": text, "wordCount": len(text.split())}
        
    except Exception as e:
        print(f"[Render] Primary extraction blocked. Engaging Massive Fallback Array. Error: {str(e)}")
        
        # ATTEMPT 2: Massive Proxy Network Fallback (12 Highly-Active Instances)
        piped_instances = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.adminforge.de",
            "https://pipedapi.drgns.space",
            "https://piped-api.garudalinux.org",
            "https://piped-api.lunar.icu",
            "https://pi.ggtyler.dev",
            "https://piped.mha.fi",
            "https://api.piped.privacydev.net",
            "https://pipedapi.r4fo.com",
            "https://pipedapi.tokhmi.xyz",
            "https://pipedapi.smnz.de"
        ]
        
        for instance in piped_instances:
            try:
                # 5-second timeout so it quickly skips dead servers
                res = requests.get(f"{instance}/streams/{video_id}", timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    subs = data.get("subtitles", [])
                    
                    en_sub = next((s for s in subs if 'en' in s.get("code", "").lower() or 'english' in s.get("name", "").lower()), None)
                    if not en_sub and subs:
                        en_sub = subs[0]
                        
                    if en_sub:
                        vtt_res = requests.get(en_sub["url"], timeout=5)
                        clean_text = clean_vtt(vtt_res.text)
                        
                        if clean_text and len(clean_text) > 50:
                            print(f"[Render] Success via {instance}")
                            return {"success": True, "transcript": clean_text, "wordCount": len(clean_text.split())}
            except Exception:
                # Silently jump to the next proxy if this one times out or fails
                continue
                
        # If absolutely every proxy fails
        raise HTTPException(status_code=422, detail="YouTube is aggressively blocking extraction. Please use the Raw Text tab.")
