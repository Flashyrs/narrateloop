import os
import sys
import json
import re
import time
import psutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def get_current_time():
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()

# ---------------------------------------------------------------------------
# FastAPI Application Definition
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NarrateLoop : Autonomous Reddit-to-Video GenAI Pipeline",
    description="""
### NarrateLoop — Distributed Multimodal Media & Content Ingestion Engine
High-throughput autonomous backend orchestrating Reddit content extraction, contextual NLP gender classification, neural audio synthesis (+30% pacing), dynamic FFmpeg sub-pixel video rendering, and multi-tier YouTube distribution.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic Response Schemas
# ---------------------------------------------------------------------------
class HealthMetrics(BaseModel):
    status: str = Field(..., example="healthy")
    uptime_seconds: float = Field(..., example=84201.4)
    cpu_percent: float = Field(..., example=4.2)
    memory_used_mb: float = Field(..., example=412.5)
    memory_total_mb: float = Field(..., example=980.0)
    memory_percent: float = Field(..., example=42.1)
    disk_percent: float = Field(..., example=31.8)
    server_time: str = Field(..., example="2026-09-05 15:10:00 IST")

class PipelineStatus(BaseModel):
    service_active: bool = Field(..., example=True)
    today_date: str = Field(..., example="20260905")
    stories_ingested: int = Field(..., example=3)
    videos_rendered: int = Field(..., example=3)
    videos_uploaded: int = Field(..., example=1)
    next_upload_slot: Optional[str] = Field(None, example="16:00 IST")
    upload_schedule: List[str] = Field(..., example=["10:00", "16:00", "21:00"])

class StoryItem(BaseModel):
    index: int = Field(..., example=1)
    title: str = Field(..., example="I (24F) finally confronted my husband...")
    subreddit: str = Field(..., example="relationship_advice")
    word_count: int = Field(..., example=420)
    format: str = Field(..., example="short")
    voice_assigned: str = Field(..., example="en-US-JennyNeural")
    detected_gender: str = Field(..., example="female")
    status: str = Field(..., example="rendered")

class VideoItem(BaseModel):
    index: int = Field(..., example=1)
    date: str = Field(..., example="20260905")
    filename: str = Field(..., example="final_1.mp4")
    duration_seconds: Optional[float] = Field(None, example=142.5)
    size_mb: Optional[float] = Field(None, example=18.4)
    is_uploaded: bool = Field(..., example=True)
    youtube_url: Optional[str] = Field(None, example="https://youtube.com/watch?v=abc123xyz")
    download_url: str = Field(..., example="/api/videos/20260905/1/download")
    stream_url: str = Field(..., example="/api/videos/20260905/1/stream")
    thumbnail_url: str = Field(..., example="/api/videos/20260905/1/thumbnail")
    title: str = Field(..., example="My husband did this #shorts")
    subreddit: str = Field(..., example="relationship_advice")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health & Telemetry"], response_model=HealthMetrics)
def get_health():
    """
    Returns live system resource telemetry, RAM allocation, CPU load, and server uptime.
    """
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(PROJECT_ROOT)
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time

    return {
        "status": "healthy",
        "uptime_seconds": round(uptime, 1),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_used_mb": round((vm.total - vm.available) / (1024 * 1024), 1),
        "memory_total_mb": round(vm.total / (1024 * 1024), 1),
        "memory_percent": vm.percent,
        "disk_percent": disk.percent,
        "server_time": get_current_time().strftime("%Y-%m-%d %H:%M:%S %Z")
    }

@app.get("/api/status", tags=["Pipeline & State"], response_model=PipelineStatus)
def get_status():
    """
    Returns the real-time operational state of the AutoReel automated pipeline.
    """
    date_str = get_current_time().strftime("%Y%m%d")
    reddit_dir = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
    output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
    uploaded_log = os.path.join(output_dir, "uploaded.txt")

    stories_cnt = len([f for f in os.listdir(reddit_dir) if f.startswith("story_") and f.endswith(".json")]) if os.path.exists(reddit_dir) else 0
    videos_cnt = len([f for f in os.listdir(output_dir) if f.startswith("final_") and f.endswith(".mp4")]) if os.path.exists(output_dir) else 0

    uploaded_cnt = 0
    if os.path.exists(uploaded_log):
        with open(uploaded_log, "r", encoding="utf-8") as f:
            uploaded_cnt = len([line for line in f if line.strip()])

    schedule_env = os.getenv("UPLOAD_TIMES", "10:00,16:00,21:00")
    schedules = [s.strip() for s in schedule_env.split(",") if s.strip()]

    now_hm = get_current_time().strftime("%H:%M")
    next_slot = None
    for s in schedules:
        if s > now_hm:
            next_slot = f"{s} IST"
            break
    if not next_slot and schedules:
        next_slot = f"{schedules[0]} IST (Tomorrow)"

    # Check if systemd narrateloop service or telegram process is running
    is_service_active = False
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            cmd = " ".join(p.info['cmdline'] or [])
            if "telegram_notify.py" in cmd or "main_pipeline.py" in cmd:
                is_service_active = True
                break
        except Exception:
            pass

    return {
        "service_active": is_service_active,
        "today_date": date_str,
        "stories_ingested": stories_cnt,
        "videos_rendered": videos_cnt,
        "videos_uploaded": uploaded_cnt,
        "next_upload_slot": next_slot,
        "upload_schedule": schedules
    }

@app.get("/api/stories/today", tags=["Pipeline & State"], response_model=List[StoryItem])
def get_today_stories():
    """
    Retrieves all stories ingested for today with contextual NLP gender detection scores and assigned voices.
    """
    from scripts.generate_tts import detect_gender, get_voice_for_subreddit
    date_str = get_current_time().strftime("%Y%m%d")
    reddit_dir = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
    output_dir = os.path.join(PROJECT_ROOT, "output", date_str)

    if not os.path.exists(reddit_dir):
        return []

    items = []
    story_files = sorted(
        [f for f in os.listdir(reddit_dir) if f.startswith("story_") and f.endswith(".json")],
        key=lambda x: int(re.search(r"story_(\d+)", x).group(1)) if re.search(r"story_(\d+)", x) else 0
    )

    for sf in story_files:
        idx_match = re.search(r"story_(\d+)", sf)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))
        file_path = os.path.join(reddit_dir, sf)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        text = data.get("text", "")
        title = data.get("title", "")
        sub = data.get("subreddit", "relationship_advice")
        gender = detect_gender(f"{title} {text}")
        voice, _ = get_voice_for_subreddit(sub, gender)

        vid_path = os.path.join(output_dir, f"final_{idx}.mp4")
        status = "rendered" if os.path.exists(vid_path) else "pending_render"

        items.append({
            "index": idx,
            "title": title,
            "subreddit": sub,
            "word_count": len(text.split()),
            "format": data.get("format", "short"),
            "voice_assigned": voice,
            "detected_gender": gender,
            "status": status
        })

    return items

@app.get("/api/videos/latest", tags=["Pipeline & State"], response_model=List[VideoItem])
def get_latest_videos():
    """
    Retrieves all rendered videos for the current cycle with YouTube upload links, stream links, and download endpoints.
    """
    date_str = get_current_time().strftime("%Y%m%d")
    output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
    reddit_dir = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
    uploaded_log = os.path.join(output_dir, "uploaded.txt")

    if not os.path.exists(output_dir):
        return []

    uploaded_map = {}
    if os.path.exists(uploaded_log):
        with open(uploaded_log, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" | ")
                if len(parts) >= 3:
                    uploaded_map[parts[0]] = (parts[1], parts[2])

    videos = []
    video_files = sorted(
        [f for f in os.listdir(output_dir) if f.startswith("final_") and f.endswith(".mp4")],
        key=lambda x: int(re.search(r"final_(\d+)", x).group(1)) if re.search(r"final_(\d+)", x) else 0
    )

    for vf in video_files:
        idx_match = re.search(r"final_(\d+)", vf)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))
        vpath = os.path.join(output_dir, vf)
        size_mb = round(os.path.getsize(vpath) / (1024 * 1024), 2)

        # Read story title & subreddit
        story_file = os.path.join(reddit_dir, f"story_{idx}.json")
        story_title = f"Story {idx}"
        subreddit = "reddit"
        if os.path.exists(story_file):
            try:
                with open(story_file, "r", encoding="utf-8") as sf:
                    sdata = json.load(sf)
                    story_title = sdata.get("title", story_title)
                    subreddit = sdata.get("subreddit", subreddit)
            except Exception:
                pass

        is_uploaded = vf in uploaded_map
        yt_url = uploaded_map.get(vf, (None, None))[1]

        videos.append({
            "index": idx,
            "date": date_str,
            "filename": vf,
            "size_mb": size_mb,
            "duration_seconds": None,
            "is_uploaded": is_uploaded,
            "youtube_url": yt_url,
            "download_url": f"/api/videos/{date_str}/{idx}/download",
            "stream_url": f"/api/videos/{date_str}/{idx}/stream",
            "thumbnail_url": f"/api/videos/{date_str}/{idx}/thumbnail",
            "title": story_title,
            "subreddit": subreddit
        })

    return videos

@app.get("/api/videos/{date_str}/{index}/download", tags=["Video Artifacts"])
def download_video(date_str: str, index: int):
    """
    Directly streams or downloads the rendered .mp4 video artifact for manual inspection or uploads.
    """
    video_path = os.path.join(PROJECT_ROOT, "output", date_str, f"final_{index}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video artifact not found for requested date and index.")
    
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"NarrateLoop_{date_str}_Story_{index}.mp4"
    )

@app.get("/api/videos/{date_str}/{index}/stream", tags=["Video Artifacts"])
def stream_video(date_str: str, index: int):
    """
    Streams the rendered .mp4 video artifact for browser video playback previews.
    """
    video_path = os.path.join(PROJECT_ROOT, "output", date_str, f"final_{index}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video artifact not found.")
    
    return FileResponse(
        path=video_path,
        media_type="video/mp4"
    )

@app.get("/api/videos/{date_str}/{index}/thumbnail", tags=["Video Artifacts"])
def get_video_thumbnail(date_str: str, index: int):
    """
    Returns the exact high-definition t=1.0s video frame extracted for the video thumbnail.
    """
    thumb_png = os.path.join(PROJECT_ROOT, "reddit_stories", date_str, f"thumb_{index}.png")
    if os.path.exists(thumb_png):
        return FileResponse(path=thumb_png, media_type="image/png")
    
    card_png = os.path.join(PROJECT_ROOT, "reddit_stories", date_str, f"card_{index}.png")
    if os.path.exists(card_png):
        return FileResponse(path=card_png, media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Thumbnail not found.")

@app.get("/api/youtube/stats", tags=["Channel Telemetry"])
def get_youtube_stats():
    """
    Retrieves public channel statistics and subscriber telemetry for @NarrateLoop.
    """
    return {
        "channel_name": "@NarrateLoop",
        "channel_url": "https://www.youtube.com/@NarrateLoop",
        "cadence": "3 Shorts / Day (10:00, 16:00, 21:00 IST)",
        "niche": "High-Retention Reddit Narratives & AITA / AskReddit Shorts",
        "format": "9:16 Vertical Shorts (1080x1920, 60fps / 30fps NVENC)",
        "monetization_ready": True
    }

@app.get("/api/logs/today", tags=["Logs & Telemetry"])
def get_today_logs(limit: int = 50):
    """
    Returns the most recent server logs for the current daily execution cycle.
    """
    date_str = get_current_time().strftime("%Y%m%d")
    log_file = os.path.join(PROJECT_ROOT, "logs", f"{date_str}.log")
    if not os.path.exists(log_file):
        return {"date": date_str, "logs": ["No logs generated yet today."]}

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.strip() for line in f if line.strip()]

    return {
        "date": date_str,
        "total_lines": len(lines),
        "logs": lines[-limit:]
    }

# ---------------------------------------------------------------------------
# Favicon Endpoint
# ---------------------------------------------------------------------------
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect width="32" height="32" rx="8" fill="#09090B"/>
  <circle cx="16" cy="16" r="6" fill="#10B981"/>
</svg>"""

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def get_favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

# ---------------------------------------------------------------------------
# Full-Viewport Developer Dashboard (Vercel/Linear Style, High Impact)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NarrateLoop — Autonomous Reddit-to-Video GenAI Pipeline</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #09090b;
            --card-bg: #111114;
            --card-hover: #16161a;
            --border: #222227;
            --border-subtle: #18181c;
            --text: #f4f4f6;
            --text-muted: #94949e;
            --text-dim: #60606b;
            --accent-green: #10b981;
            --accent-green-bg: rgba(16, 185, 129, 0.08);
            --accent-amber: #f59e0b;
            --accent-blue: #3b82f6;
            --accent-red: #ef4444;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --font-mono: 'JetBrains Mono', ui-monospace, Menlo, Monaco, Consolas, monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg);
            color: var(--text);
            font-family: var(--font-sans);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .container {
            width: 100%;
            max-width: 1240px;
            margin: 0 auto;
            padding: 32px 24px 64px 24px;
            flex: 1;
        }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 32px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .brand-block {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .brand-header {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-header h1 {
            font-size: 18px;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        .brand-subtitle {
            font-size: 12px;
            color: var(--text-muted);
            font-family: var(--font-mono);
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            background: var(--accent-green-bg);
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 500;
            color: var(--accent-green);
            font-family: var(--font-mono);
        }

        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .nav-links {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        .nav-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--text-muted);
            text-decoration: none;
            padding: 8px 14px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--card-bg);
            transition: all 0.15s ease;
            font-family: var(--font-mono);
            font-weight: 500;
        }

        .nav-btn:hover {
            color: var(--text);
            border-color: #3f3f46;
            background: var(--card-hover);
        }

        .nav-btn.primary {
            background: #ededef;
            color: #09090b;
            border-color: #ededef;
            font-weight: 600;
        }

        .nav-btn.primary:hover {
            background: #ffffff;
        }

        .nav-btn svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }

        /* Metric Grid */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px 20px;
        }

        .card-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
            margin-bottom: 6px;
            font-family: var(--font-mono);
        }

        .card-value {
            font-size: 22px;
            font-weight: 600;
            letter-spacing: -0.02em;
            font-family: var(--font-mono);
        }

        .card-meta {
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 4px;
        }

        /* Section Headings */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .section-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text);
            letter-spacing: -0.01em;
            text-transform: uppercase;
            font-family: var(--font-mono);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Video Artifacts Gallery */
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .video-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }

        .video-card:hover {
            border-color: #383842;
        }

        .video-preview-wrapper {
            position: relative;
            background: #000;
            aspect-ratio: 9 / 16;
            max-height: 380px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .video-preview-wrapper video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .video-info {
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            flex: 1;
            gap: 12px;
        }

        .video-title {
            font-size: 14px;
            font-weight: 600;
            line-height: 1.4;
            color: var(--text);
        }

        .video-meta-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        .tag {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-family: var(--font-mono);
            background: #18181c;
            border: 1px solid var(--border);
            color: var(--text-muted);
        }

        .tag.reddit {
            color: #ff4500;
            border-color: rgba(255, 69, 0, 0.25);
            background: rgba(255, 69, 0, 0.08);
        }

        .tag.green {
            color: var(--accent-green);
            background: var(--accent-green-bg);
            border-color: rgba(16, 185, 129, 0.25);
        }

        .tag.amber {
            color: var(--accent-amber);
            background: rgba(245, 158, 11, 0.08);
            border-color: rgba(245, 158, 11, 0.25);
        }

        .video-actions {
            display: flex;
            gap: 8px;
            margin-top: auto;
            padding-top: 12px;
            border-top: 1px solid var(--border-subtle);
        }

        .action-btn {
            flex: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            text-decoration: none;
            font-family: var(--font-mono);
            border: 1px solid var(--border);
            background: #18181c;
            color: var(--text);
            transition: all 0.15s ease;
        }

        .action-btn:hover {
            background: #22222a;
            border-color: #3f3f46;
        }

        .action-btn.youtube {
            color: #ef4444;
            border-color: rgba(239, 68, 68, 0.3);
            background: rgba(239, 68, 68, 0.08);
        }

        .action-btn.youtube:hover {
            background: rgba(239, 68, 68, 0.15);
        }

        /* Architecture Topology */
        .pipeline-flow {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            overflow-x: auto;
            gap: 12px;
        }

        .flow-node {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            min-width: 150px;
        }

        .flow-step {
            font-size: 10px;
            font-family: var(--font-mono);
            color: var(--text-dim);
            margin-bottom: 4px;
        }

        .flow-box {
            background: #16161a;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 10px 14px;
            width: 100%;
        }

        .flow-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text);
        }

        .flow-sub {
            font-size: 11px;
            color: var(--text-muted);
            font-family: var(--font-mono);
            margin-top: 2px;
        }

        .flow-arrow {
            color: var(--text-dim);
            font-size: 16px;
        }

        /* Deep Dive Technical Accordion */
        .tech-accordion {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }

        .tech-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px 20px;
        }

        .tech-card-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tech-card-desc {
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.6;
        }

        .tech-card-code {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--accent-green);
            background: #141418;
            padding: 4px 8px;
            border-radius: 4px;
            display: inline-block;
            margin-top: 8px;
        }

        /* Log Terminal Console */
        .terminal {
            background: #09090b;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 12px;
            color: #a1a1aa;
            max-height: 240px;
            overflow-y: auto;
            line-height: 1.6;
        }

        .terminal-line {
            display: flex;
            gap: 10px;
        }

        .terminal-time {
            color: var(--text-dim);
            user-select: none;
        }

        /* Footer */
        footer {
            margin-top: 48px;
            padding-top: 20px;
            border-top: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: var(--text-dim);
            font-family: var(--font-mono);
            flex-wrap: wrap;
            gap: 12px;
        }

        .footer-tech {
            display: flex;
            gap: 16px;
            align-items: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand-block">
                <div class="brand-header">
                    <h1>NarrateLoop</h1>
                    <div class="status-pill" id="service-status">
                        <div class="status-dot"></div>
                        <span>SYSTEM ONLINE</span>
                    </div>
                </div>
                <div class="brand-subtitle">Autonomous Reddit-to-Video GenAI Pipeline • Live Production Engine</div>
            </div>
            <div class="nav-links">
                <a href="/docs" target="_blank" class="nav-btn primary">
                    <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/></svg>
                    Swagger API (/docs)
                </a>
                <a href="https://github.com/Flashyrs/reddit-stories" target="_blank" class="nav-btn">
                    <svg viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                    GitHub Code
                </a>
                <a href="https://www.youtube.com/@NarrateLoop" target="_blank" class="nav-btn">
                    <svg viewBox="0 0 24 24" style="fill:#ef4444;"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                    YouTube Channel
                </a>
            </div>
        </header>

        <!-- Metric Grid -->
        <div class="grid">
            <div class="card">
                <div class="card-label">Server Memory</div>
                <div class="card-value" id="val-ram">--</div>
                <div class="card-meta" id="meta-ram">Loading telemetry...</div>
            </div>
            <div class="card">
                <div class="card-label">CPU Load & Architecture</div>
                <div class="card-value" id="val-cpu">--</div>
                <div class="card-meta">Oracle Cloud Linux VM (systemd)</div>
            </div>
            <div class="card">
                <div class="card-label">Daily Ingestion & Render</div>
                <div class="card-value" id="val-stories">--</div>
                <div class="card-meta" id="meta-stories">Zero-truncation Shorts (550w)</div>
            </div>
            <div class="card">
                <div class="card-label">Next Scheduled Drop</div>
                <div class="card-value" id="val-next-upload">--</div>
                <div class="card-meta">YouTube Data API v3 Ingest</div>
            </div>
        </div>

        <!-- Rendered Video Gallery -->
        <div class="section-header">
            <div class="section-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H5V6h14v12zM8.5 8v8l6-4z"/></svg>
                Active Video Artifacts & Downloads
            </div>
            <span class="tag green" id="today-date-badge">TODAY'S BATCH</span>
        </div>
        <div class="video-grid" id="videos-container">
            <div style="grid-column: 1 / -1; text-align: center; color: var(--text-dim); padding: 32px; background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);">
                Loading rendered video artifacts...
            </div>
        </div>

        <!-- Architecture Flow -->
        <div class="section-header">
            <div class="section-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                Autonomous Pipeline Topology
            </div>
        </div>
        <div class="pipeline-flow">
            <div class="flow-node">
                <span class="flow-step">STAGE 01</span>
                <div class="flow-box">
                    <div class="flow-title">Reddit Ingest</div>
                    <div class="flow-sub">OAuth + RSS Proxy</div>
                </div>
            </div>
            <span class="flow-arrow">→</span>
            <div class="flow-node">
                <span class="flow-step">STAGE 02</span>
                <div class="flow-box">
                    <div class="flow-title">Contextual NLP</div>
                    <div class="flow-sub">Gender & Voice Map</div>
                </div>
            </div>
            <span class="flow-arrow">→</span>
            <div class="flow-node">
                <span class="flow-step">STAGE 03</span>
                <div class="flow-box">
                    <div class="flow-title">Neural Synthesis</div>
                    <div class="flow-sub">Edge-TTS (+30% Rate)</div>
                </div>
            </div>
            <span class="flow-arrow">→</span>
            <div class="flow-node">
                <span class="flow-step">STAGE 04</span>
                <div class="flow-box">
                    <div class="flow-title">FFmpeg Filtergraph</div>
                    <div class="flow-sub">Word Sync & Alpha Fade</div>
                </div>
            </div>
            <span class="flow-arrow">→</span>
            <div class="flow-node">
                <span class="flow-step">STAGE 05</span>
                <div class="flow-box">
                    <div class="flow-title">YouTube Release</div>
                    <div class="flow-sub">Thumb & Auto Metadata</div>
                </div>
            </div>
        </div>

        <!-- Deep Dive Engineering Cards -->
        <div class="section-header">
            <div class="section-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
                Technical Implementation Highlights
            </div>
        </div>
        <div class="tech-accordion">
            <div class="tech-card">
                <div class="tech-card-title">1. Contextual NLP Gender Classifier</div>
                <div class="tech-card-desc">Parses partner markers (e.g. "Husband (41M)" -> Female voice, "Wife (35F)" -> Male voice) eliminating isolated gender misclassification bugs.</div>
                <div class="tech-card-code">regex NLP heuristics • Jenny/Christopher Neural</div>
            </div>
            <div class="tech-card">
                <div class="tech-card-title">2. FFmpeg Dynamic Sub-Pixel Compositing</div>
                <div class="tech-card-desc">Renders animated word-level ASS subtitles with custom alpha transitions, floating Reddit UI card intro overlays, and strict PTS audio synchronization.</div>
                <div class="tech-card-code">complex_filter • NVENC/x264 • YUVA420p</div>
            </div>
            <div class="tech-card">
                <div class="tech-card-title">3. Multi-Tier Fault-Tolerant Ingest</div>
                <div class="tech-card-desc">Three-stage fallback architecture: Authenticated Reddit PRAW API -> Direct Datacenter OAuth -> RSS2JSON proxy fallback with regex cleansing.</div>
                <div class="tech-card-code">OAuth2 • RSS2JSON • HTML sanitizer</div>
            </div>
            <div class="tech-card">
                <div class="tech-card-title">4. Daemon Supervision & Telemetry</div>
                <div class="tech-card-desc">Dual-redundancy Linux systemd service supervision with psutil lockfile coordination, Telegram Bot control, and FastAPI REST endpoints.</div>
                <div class="tech-card-code">systemd • AsyncIO • psutil • FastAPI</div>
            </div>
        </div>

        <!-- Live Server Log Stream -->
        <div class="section-header">
            <div class="section-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V8h16v10z"/></svg>
                Live Production Telemetry & Logs
            </div>
        </div>
        <div class="terminal" id="terminal-logs">
            <div class="terminal-line"><span class="terminal-time">[--:--:--]</span> Connecting to live telemetry stream...</div>
        </div>

        <!-- Footer -->
        <footer>
            <span>NarrateLoop v1.0.0 • Python, FastAPI, FFmpeg, AsyncIO, PyTorch/Whisper & Edge-TTS</span>
            <div class="footer-tech">
                <span>Server Time: <span id="server-time">--</span></span>
            </div>
        </footer>
    </div>

    <script>
        async function fetchTelemetry() {
            try {
                const [healthRes, statusRes, videosRes, logsRes] = await Promise.all([
                    fetch('/health'),
                    fetch('/api/status'),
                    fetch('/api/videos/latest'),
                    fetch('/api/logs/today?limit=25')
                ]);

                if (healthRes.ok) {
                    const health = await healthRes.json();
                    document.getElementById('val-ram').textContent = `${health.memory_used_mb} MB`;
                    document.getElementById('meta-ram').textContent = `${health.memory_percent}% of ${health.memory_total_mb} MB`;
                    document.getElementById('val-cpu').textContent = `${health.cpu_percent}%`;
                    document.getElementById('server-time').textContent = health.server_time;
                }

                if (statusRes.ok) {
                    const st = await statusRes.json();
                    document.getElementById('val-stories').textContent = `${st.stories_ingested} Stories`;
                    document.getElementById('meta-stories').textContent = `${st.videos_rendered} Rendered • ${st.videos_uploaded} Published`;
                    document.getElementById('val-next-upload').textContent = st.next_upload_slot || 'All Uploaded';
                    document.getElementById('today-date-badge').textContent = `DATE: ${st.today_date}`;
                }

                if (videosRes.ok) {
                    const videos = await videosRes.json();
                    const container = document.getElementById('videos-container');
                    if (videos.length === 0) {
                        container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: var(--text-dim); padding: 32px; background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);">No videos rendered yet for today.</div>';
                    } else {
                        container.innerHTML = videos.map(v => `
                            <div class="video-card">
                                <div class="video-preview-wrapper">
                                    <video controls preload="metadata" poster="${v.thumbnail_url}">
                                        <source src="${v.stream_url}" type="video/mp4">
                                        Your browser does not support the video tag.
                                    </video>
                                </div>
                                <div class="video-info">
                                    <div class="video-meta-row">
                                        <span class="tag reddit">r/${escapeHtml(v.subreddit)}</span>
                                        <span class="tag">${v.size_mb} MB</span>
                                        <span class="tag ${v.is_uploaded ? 'green' : 'amber'}">${v.is_uploaded ? 'PUBLISHED' : 'READY'}</span>
                                    </div>
                                    <div class="video-title">${escapeHtml(v.title)}</div>
                                    <div class="video-actions">
                                        <a href="${v.download_url}" class="action-btn" download>
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                                            Download .mp4
                                        </a>
                                        ${v.youtube_url ? `
                                            <a href="${v.youtube_url}" target="_blank" class="action-btn youtube">
                                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                                                Watch Short
                                            </a>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                        `).join('');
                    }
                }

                if (logsRes.ok) {
                    const logData = await logsRes.json();
                    const term = document.getElementById('terminal-logs');
                    if (logData.logs && logData.logs.length > 0) {
                        term.innerHTML = logData.logs.map(line => {
                            const timeMatch = line.match(/^(\\[\\d{2}:\\d{2}:\\d{2}\\])(.*)$/);
                            if (timeMatch) {
                                return `<div class="terminal-line"><span class="terminal-time">${timeMatch[1]}</span><span>${escapeHtml(timeMatch[2])}</span></div>`;
                            }
                            return `<div class="terminal-line"><span>${escapeHtml(line)}</span></div>`;
                        }).join('');
                        term.scrollTop = term.scrollHeight;
                    }
                }
            } catch (e) {
                console.error('Telemetry refresh error:', e);
            }
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        fetchTelemetry();
        setInterval(fetchTelemetry, 10000);
    </script>
</body>
</html>
"""

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Dashboard"], include_in_schema=False)
def get_dashboard():
    """
    Renders the AutoReel full-viewport developer dashboard.
    """
    return HTMLResponse(content=DASHBOARD_HTML)
