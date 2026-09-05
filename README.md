# 🎬 NarrateLoop : Autonomous Reddit-to-Video GenAI Pipeline

[![Live Dashboard](https://img.shields.io/badge/Live_Dashboard-https%3A%2F%2Fnarrateloop.duckdns.org-10b981?style=for-the-badge&logo=fastapi)](https://narrateloop.duckdns.org)
[![Interactive API Docs](https://img.shields.io/badge/Swagger_OpenAPI-%2Fdocs-3b82f6?style=for-the-badge&logo=swagger)](https://narrateloop.duckdns.org/docs)
[![YouTube Channel](https://img.shields.io/badge/YouTube-%40NarrateLoop-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@NarrateLoop)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FFmpeg NVENC](https://img.shields.io/badge/FFmpeg-GPU_NVENC-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)

**NarrateLoop** is an autonomous, high-throughput media generation and distributed content ingestion engine. It transforms raw text stories from Reddit into viral, high-retention 9:16 vertical YouTube Shorts and 16:9 videos using contextual NLP gender classification, neural audio synthesis (+30% pacing), word-level dynamic ASS subtitle overlays, GPU-accelerated FFmpeg compositing, and automated multi-tier YouTube distribution.

Deployed 24/7 on an **Oracle Cloud Linux VM** with dual-redundancy `systemd` process supervision, SQLite asset tracking, and real-time Telegram remote telemetry.

---

## 🏛️ System Architecture Topology

```
                                  [ Reddit API / RSS Proxy ]
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Stage 1: Story Ingest  │  (PRAW / OAuth / RSS Fallback)
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Stage 2: Context NLP   │  (Relationship Heuristics &
                                 │      Gender Classifier  │   Gemini Title Generation)
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Stage 3: Neural Voice  │  (Edge-TTS / Bark +30% Rate
                                 │     & Whisper Timing    │   Word-Level Exact Timestamps)
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Stage 4: FFmpeg Engine │  (Dynamic ASS/SSA Subtitles,
                                 │   GPU NVENC Compositing │   Alpha Card Fade, PTS Sync)
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Stage 5: Distribution  │  (YouTube Data API v3 &
                                 │   & Remote Telemetry    │   Telegram Remote Daemon)
                                 └────────────┬────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
       [ Telegram Bot Remote CLI ]                       [ FastAPI Telemetry & Dashboard ]
        (/start, /upload, /status)                         (https://narrateloop.duckdns.org)
```

---

## ⚡ How It Works (Engineering Deep-Dive)

### 1. Fault-Tolerant Multimodal Ingest (`fetch_reddit.py`)
* **Multi-Tier Failover**:
  1. Authenticated Reddit PRAW API.
  2. Direct Datacenter OAuth token negotiation (designed for Cloud IPs).
  3. RSS2JSON XML-to-JSON proxy feed parser for 100% cloud reliability.
* **Text Cleansing & Formatting**: Regex pipeline removes markdown hyperlinks, URLs, subreddit headers, and user attribution tags (`/u/...`), preventing extraneous artifacts during TTS synthesis.
* **Full-Length Preservation**: Stories up to **550 words** (~2.45 to 3.00 minutes at +30% pacing) are ingested with 100% zero sentence truncation.

### 2. Contextual NLP Gender & Voice Modeling (`generate_tts.py`)
* **Partner & Self-Identification Parsing**: Analyzes relationship markers (e.g. *"Husband (41M)"* / *"my boyfriend"* indicates a **female** narrator assigned `en-US-JennyNeural`, whereas *"Wife (35F)"* / *"my girlfriend"* indicates a **male** narrator assigned `en-US-ChristopherNeural`).
* **Subreddit-Specific Tone Tuning**: Custom neural voice mapping tailored per subreddit genre (`r/tifu` gets energetic pacing; `r/confessions` gets reflective pacing).

### 3. Neural Speech Synthesis & Word-Level Alignment (`generate_subs.py`)
* **High-Pacing Narration**: Speech rate accelerated to **`+30%`** for snappy short-form retention.
* **Dynamic ASS Subtitle Engine**: Generates Advanced SubStation Alpha (`.ass`) files with word-level highlight timing (`&H0000FFFF` rhythm yellow and `&H000000FF` emphasis red), exact font scaling, and safety margins to eliminate subtitle drift.

### 4. GPU-Accelerated FFmpeg Sub-Pixel Video Compositing (`render_video.py`)
* **Filtergraph Execution**:
  * Scales & crops 60fps/30fps gameplay backgrounds to vertical 9:16 (1080x1920).
  * Overlays floating Reddit UI card with smooth alpha-channel fade (`fade=t=out:st=2.6:d=0.4`).
  * Burns synchronized word-level ASS subtitles directly into video streams.
  * Encodes using `h264_nvenc` (NVIDIA GPU hardware acceleration) with `libx264` ultrafast CPU fallback.
* **Automatic High-Definition Thumbnail Frame Extraction**: Takes an exact snapshot from the rendered video at $t = 1.0\text{s}$ (`thumb_{idx}.png`) showing the moving background and crisp floating card.

### 5. Asynchronous Distribution & Daemon Supervision (`telegram_notify.py` & `api/main.py`)
* **Automated Cron Scheduling**: Daily ingestion at 02:00 IST with three automated daily YouTube release slots (10:00, 16:00, 21:00 IST).
* **Dual-Redundancy Process Coordination**: Supervised under Linux `systemd` with `psutil` PID lockfile coordination to prevent duplicate concurrent renders.
* **Live Telemetry & Dashboard**: FastAPI REST API providing hardware metrics, story feeds, video artifact downloads, and Swagger `/docs`.

---

## 🛠️ Tech Stack & Skills

| Domain | Technologies |
|---|---|
| **Backend & APIs** | Python 3.12, FastAPI, Uvicorn, AsyncIO, Pydantic, RESTful API |
| **Machine Learning & NLP** | PyTorch, OpenAI Whisper (word-level alignment), Suno Bark TTS, Microsoft Edge-TTS, Google Gemini NLP |
| **Media Processing** | FFmpeg (NVENC GPU hardware acceleration, Filtergraphs, ASS/SSA Subtitles), Pydub, Wave |
| **Infrastructure & Cloud** | Linux (Ubuntu on Oracle Cloud OCI), `systemd` daemons, Nginx reverse proxy, Let's Encrypt SSL, Certbot, DuckDNS |
| **Data & Storage** | SQLite, GPUtil (GPU VRAM monitoring & CUDA OOM CPU fallback), JSON file store |
| **Automation & APIs** | YouTube Data API v3, Reddit PRAW & OAuth API, Telegram Bot API |

---

## 📂 Project Structure

```
AutoReel/
├── api/
│   ├── main.py                     # FastAPI REST API & Vercel-style developer dashboard
│   └── __init__.py
├── scripts/
│   ├── fetch_reddit.py             # Multi-tier Reddit ingest & 550w story preservation
│   ├── generate_tts.py             # NLP gender detection & neural speech synthesis (+30%)
│   ├── generate_subs.py            # Dynamic ASS/SSA subtitle compiler with word sync
│   ├── render_video.py             # FFmpeg filtergraph engine & frame thumbnail extraction
│   ├── upload_to_youtube.py        # YouTube Data API v3 upload & metadata manager
│   ├── upload_pending.py           # Scheduled automated slot dispatcher
│   ├── telegram_notify.py          # Asynchronous remote supervision bot & scheduler
│   └── narrateloop-api.service     # Linux systemd unit service file
├── utils/
│   ├── title_utils.py              # Google Gemini AI title generator
│   ├── thumbnail_utils.py          # Pillow/Playwright Reddit card renderer
│   └── youtube_utils.py            # YouTube quota & upload validator
├── main_pipeline.py                # Core orchestration pipeline & structured logging
├── requirements.txt                # Python dependencies
└── README.md                       # Documentation
```

---

## 🚀 Live Endpoints & Usage

* **Live Dashboard**: [https://narrateloop.duckdns.org](https://narrateloop.duckdns.org)
* **Interactive Swagger UI**: [https://narrateloop.duckdns.org/docs](https://narrateloop.duckdns.org/docs)
* **ReDoc API Reference**: [https://narrateloop.duckdns.org/redoc](https://narrateloop.duckdns.org/redoc)

### REST Endpoints
* `GET /health` — Real-time server telemetry (RAM %, CPU load, disk usage, uptime).
* `GET /api/status` — Operational status, queue metrics, and next scheduled upload time.
* `GET /api/stories/today` — Ingested stories with NLP gender score and assigned neural voice.
* `GET /api/videos/latest` — Rendered video artifacts with stream links and YouTube URLs.
* `GET /api/videos/{date}/{index}/download` — Direct `.mp4` video artifact download.
* `GET /api/logs/today` — Live server execution logs stream.

---

## 📜 Resume Bullet Points (FAANG SDE-1 / Software Engineer)

> **NarrateLoop — Autonomous Reddit-to-Video GenAI Pipeline**  
> *Python • FastAPI • FFmpeg (NVENC) • PyTorch • Whisper • Bark • SQLite • Linux (systemd) • Oracle Cloud*  
> * [Live Dashboard & Swagger Docs: https://narrateloop.duckdns.org/docs]  
> * [GitHub Repository: https://github.com/Flashyrs/reddit-stories]  
>
> * **Built a 24/7 autonomous multimodal GenAI pipeline** deployed on Oracle Cloud, orchestrating Reddit content extraction, Gemini NLP metadata cleansing, neural speech synthesis (+30% pacing), and automated YouTube distribution with zero human intervention.
> * **Implemented GPU-accelerated video rendering via FFmpeg NVENC** with sub-pixel overlay placement, dynamic alpha transitions, and dynamic ASS/SSA word-synchronized subtitle highlighting across 100+ production renders.
> * **Engineered speech synthesis & alignment systems** leveraging Suno Bark, Edge-TTS, and Whisper word-level alignment with GPUtil VRAM monitoring and automated CPU fallback on CUDA OOM.
> * **Designed fault-tolerant ingest pipelines** featuring 3-tier fallback (PRAW OAuth to direct datacenter tokens to RSS proxies) and dual-redundancy Linux `systemd` supervision with `psutil` concurrency coordination.
> * **Developed a high-performance FastAPI telemetry service** exposing interactive Swagger `/docs`, video artifact streaming/download endpoints, and automated Let's Encrypt SSL reverse-proxied through Nginx.

---

## 📄 License
MIT License. Open source and built for high-throughput multimodal streaming.
