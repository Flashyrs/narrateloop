import os
import sys
import json
import re
import time
import psutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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
    title="NarrateLoop Engine API",
    description="""
### Autonomous Multimodal Media & Content Ingestion Pipeline
High-throughput automated backend orchestrating Reddit content extraction, contextual NLP gender classification, neural audio synthesis (+30% pacing), dynamic FFmpeg sub-pixel rendering, and multi-tier YouTube distribution.
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
    server_time: str = Field(..., example="2026-09-05 13:55:00 IST")

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
    filename: str = Field(..., example="final_1.mp4")
    duration_seconds: Optional[float] = Field(None, example=142.5)
    size_mb: Optional[float] = Field(None, example=18.4)
    is_uploaded: bool = Field(..., example=True)
    youtube_url: Optional[str] = Field(None, example="https://youtube.com/watch?v=abc123xyz")
    title: str = Field(..., example="My husband did this #shorts")

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
    Returns the real-time operational state of the NarrateLoop automated pipeline.
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
    Retrieves all rendered videos for the current cycle with YouTube upload links and stream properties.
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

        # Read story title
        story_file = os.path.join(reddit_dir, f"story_{idx}.json")
        story_title = f"Story {idx}"
        if os.path.exists(story_file):
            try:
                with open(story_file, "r", encoding="utf-8") as sf:
                    story_title = json.load(sf).get("title", story_title)
            except Exception:
                pass

        is_uploaded = vf in uploaded_map
        yt_url = uploaded_map.get(vf, (None, None))[1]

        videos.append({
            "index": idx,
            "filename": vf,
            "size_mb": size_mb,
            "duration_seconds": None,
            "is_uploaded": is_uploaded,
            "youtube_url": yt_url,
            "title": story_title
        })

    return videos

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
# Minimal Developer Dashboard (Single Clean Page, No Generic AI fluff)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NarrateLoop — Engine Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #09090b;
            --card-bg: #121215;
            --border: #222227;
            --border-subtle: #18181c;
            --text: #ededef;
            --text-muted: #8e8e99;
            --text-dim: #5c5c66;
            --accent-green: #10b981;
            --accent-green-bg: rgba(16, 185, 129, 0.1);
            --accent-amber: #f59e0b;
            --accent-blue: #3b82f6;
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
            padding: 32px 20px;
        }

        .container {
            max-width: 1040px;
            margin: 0 auto;
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

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand h1 {
            font-size: 18px;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            background: var(--accent-green-bg);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 9999px;
            font-size: 12px;
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
            gap: 12px;
            align-items: center;
        }

        .nav-link {
            font-size: 13px;
            color: var(--text-muted);
            text-decoration: none;
            padding: 6px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--card-bg);
            transition: all 0.15s ease;
            font-family: var(--font-mono);
        }

        .nav-link:hover {
            color: var(--text);
            border-color: #3f3f46;
        }

        .nav-link.primary {
            background: #ededef;
            color: #09090b;
            border-color: #ededef;
            font-weight: 500;
        }

        .nav-link.primary:hover {
            background: #ffffff;
        }

        /* Metric Grid */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
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

        /* Architecture Flow */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text);
            letter-spacing: -0.01em;
            text-transform: uppercase;
            font-family: var(--font-mono);
        }

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
            min-width: 140px;
        }

        .flow-step {
            font-size: 10px;
            font-family: var(--font-mono);
            color: var(--text-dim);
            margin-bottom: 4px;
        }

        .flow-box {
            background: #18181c;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 10px 14px;
            width: 100%;
        }

        .flow-title {
            font-size: 13px;
            font-weight: 500;
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

        /* Table & Lists */
        .panel {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 32px;
        }

        .panel-header {
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .panel-title {
            font-size: 13px;
            font-weight: 600;
            font-family: var(--font-mono);
            color: var(--text);
            text-transform: uppercase;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }

        th {
            background: #141418;
            padding: 10px 20px;
            color: var(--text-muted);
            font-weight: 500;
            font-size: 11px;
            text-transform: uppercase;
            font-family: var(--font-mono);
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 14px 20px;
            border-bottom: 1px solid var(--border-subtle);
            color: var(--text);
        }

        tr:last-child td {
            border-bottom: none;
        }

        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-family: var(--font-mono);
            background: #1c1c22;
            border: 1px solid var(--border);
            color: var(--text-muted);
        }

        .tag.green {
            color: var(--accent-green);
            background: var(--accent-green-bg);
            border-color: rgba(16, 185, 129, 0.2);
        }

        .tag.amber {
            color: var(--accent-amber);
            background: rgba(245, 158, 11, 0.1);
            border-color: rgba(245, 158, 11, 0.2);
        }

        /* Log Console */
        .terminal {
            background: #09090b;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 12px;
            color: #a1a1aa;
            max-height: 260px;
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
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand">
                <h1>NarrateLoop</h1>
                <div class="status-pill" id="service-status">
                    <div class="status-dot"></div>
                    <span>SYSTEM ONLINE</span>
                </div>
            </div>
            <div class="nav-links">
                <a href="/docs" target="_blank" class="nav-link primary">Swagger API (/docs)</a>
                <a href="https://github.com/Flashyrs/reddit-stories" target="_blank" class="nav-link">GitHub</a>
                <a href="https://www.youtube.com/@NarrateLoop" target="_blank" class="nav-link">YouTube Channel</a>
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
                <div class="card-label">CPU Utilization</div>
                <div class="card-value" id="val-cpu">--</div>
                <div class="card-meta">Oracle Cloud Linux VM</div>
            </div>
            <div class="card">
                <div class="card-label">Daily Ingestion</div>
                <div class="card-value" id="val-stories">--</div>
                <div class="card-meta" id="meta-stories">Zero-truncation Shorts</div>
            </div>
            <div class="card">
                <div class="card-label">Next Scheduled Upload</div>
                <div class="card-value" id="val-next-upload">--</div>
                <div class="card-meta">YouTube Data API v3</div>
            </div>
        </div>

        <!-- Architecture Flow -->
        <div class="section-header">
            <div class="section-title">Automated Pipeline Topology</div>
        </div>
        <div class="pipeline-flow">
            <div class="flow-node">
                <span class="flow-step">STAGE 01</span>
                <div class="flow-box">
                    <div class="flow-title">Reddit Ingestion</div>
                    <div class="flow-sub">OAuth & RSS Proxy</div>
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
                    <div class="flow-title">Neural TTS Synthesis</div>
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
                    <div class="flow-sub">Auto Metadata & Thumb</div>
                </div>
            </div>
        </div>

        <!-- Stories Ingested Table -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">Active Daily Queue</div>
                <span class="tag green" id="queue-date">TODAY</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Slot</th>
                        <th>Subreddit & Title</th>
                        <th>Words</th>
                        <th>Voice Profile</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="stories-tbody">
                    <tr>
                        <td colspan="5" style="text-align: center; color: var(--text-dim);">Loading ingested stories...</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Live Server Log Stream -->
        <div class="section-header">
            <div class="section-title">Telemetry & Execution Logs</div>
        </div>
        <div class="terminal" id="terminal-logs">
            <div class="terminal-line"><span class="terminal-time">[--:--:--]</span> Initializing telemetry stream...</div>
        </div>

        <!-- Footer -->
        <footer>
            <span>NarrateLoop v1.0.0 • Architecture: Python, FFmpeg, AsyncIO, Linux systemd</span>
            <span>Server Time: <span id="server-time">--</span></span>
        </footer>
    </div>

    <script>
        async function fetchTelemetry() {
            try {
                const [healthRes, statusRes, storiesRes, logsRes] = await Promise.all([
                    fetch('/health'),
                    fetch('/api/status'),
                    fetch('/api/stories/today'),
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
                    document.getElementById('meta-stories').textContent = `${st.videos_rendered} Rendered • ${st.videos_uploaded} Uploaded`;
                    document.getElementById('val-next-upload').textContent = st.next_upload_slot || 'All Uploaded';
                    document.getElementById('queue-date').textContent = st.today_date;
                }

                if (storiesRes.ok) {
                    const stories = await storiesRes.json();
                    const tbody = document.getElementById('stories-tbody');
                    if (stories.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No active stories in current queue.</td></tr>';
                    } else {
                        tbody.innerHTML = stories.map(s => `
                            <tr>
                                <td style="font-family: var(--font-mono); font-weight: 500;">#0${s.index}</td>
                                <td>
                                    <div style="font-weight: 500; font-size: 13px;">${escapeHtml(s.title)}</div>
                                    <div style="color: var(--text-muted); font-size: 11px; font-family: var(--font-mono);">r/${escapeHtml(s.subreddit)}</div>
                                </td>
                                <td style="font-family: var(--font-mono);">${s.word_count}w</td>
                                <td>
                                    <span class="tag">${s.voice_assigned.replace('en-US-', '').replace('Neural', '')} (${s.detected_gender})</span>
                                </td>
                                <td>
                                    <span class="tag ${s.status === 'rendered' ? 'green' : 'amber'}">${s.status.toUpperCase()}</span>
                                </td>
                            </tr>
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

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"], include_in_schema=False)
def get_dashboard():
    """
    Renders the ultra-minimalist developer dashboard.
    """
    return HTMLResponse(content=DASHBOARD_HTML)
