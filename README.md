# 🎬 Reddit-to-YouTube Automation Pipeline

An end-to-end automated pipeline that converts Reddit stories into high-retention YouTube Videos and Shorts using AI voiceovers, dynamic subtitles, and gameplay backgrounds. Fully automated. Telegram-controlled. Built for scale.

---

## 🚀 What This Does

This system automatically:
- Extracts stories from Reddit
- Converts text into AI-generated voiceovers
- Generates perfectly time-aligned subtitles
- Overlays gameplay footage as background
- Renders YouTube Shorts or full-length videos
- Uploads or schedules content on YouTube
- Allows full remote control via Telegram

No manual editing. No UI dependency.

---

## 🧠 Core Features

### 🔍 Reddit Story Extraction
- Fetches stories from configurable subreddits
- Filters by score, length, and post type
- Auto-splits long stories into multiple parts
- Stores clean, structured JSON output

### 🗣️ AI Voiceover Generation
- Uses **Bark** for expressive text-to-speech
- Optional fallback TTS support
- Audio cleanup and silence trimming

### ⏱️ Accurate Timestamp Mapping
- Uses **Whisper** word-level timestamps
- One-to-one mapping between spoken audio and original text
- Guarantees subtitle accuracy
- Zero hallucinated or skipped words

### 📝 Dynamic Subtitle Generation
- Generates `.ass` subtitle files
- Shorts:
  - Single-word subtitles
  - Center aligned
- Videos:
  - 2–3 word grouped subtitles
- Highlighting and emphasis supported
- Timing driven directly by Whisper output

### 🎮 Gameplay Background Overlay
- Supports random or fixed gameplay clips
- Shorts rendered in 9:16
- Videos rendered in 16:9
- Video length auto-matches audio duration

### 📤 YouTube Upload & Scheduling
- Uses YouTube Data API
- Supports:
  - Auto-upload
  - Scheduled publishing
  - Title, description, and tag automation
- Separate handling for Shorts and long videos

### 🤖 Telegram Bot Control
- Start or stop pipeline remotely
- Upload specific story index
- Override Shorts vs Video mode
- Progress updates and error alerts
- No server access needed after setup

---

## 🧩 Tech Stack

- **Language:** Python  
- **TTS:** Bark  
- **ASR & Alignment:** Whisper (word-level timestamps)  
- **Video Processing:** FFmpeg  
- **APIs:** Reddit API, YouTube Data API, Telegram Bot API  
- **Automation:** Cron / Scheduler  
- **Subtitles:** ASS (Advanced SubStation Alpha)

---

## ⚙️ Setup

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/reddit-to-youtube-pipeline.git
cd reddit-to-youtube-pipeline
```
### 2. Install dependencies
```
pip install -r requirements.txt
```
### 3. Configure API keys
```
Update config.yaml with the following:

Reddit API credentials

YouTube Data API credentials

Telegram Bot token
```
### 4. Run the pipeline
```
python main_pipeline.py
```
###📌 Telegram Commands (Examples)
```
/start
/upload 3 short
/upload 5 video
/status
/stop
```
### 🧪 Reliability Guarantees
Every spoken word appears in subtitles

Subtitles only appear when audio is present

Video duration always matches audio

No silent frames

No subtitle drift

If this fails, your alignment logic is wrong.

### 📈 Use Cases
Reddit story YouTube channels

Automated Shorts farms

AI narration pipelines

Content scaling systems

Subtitle and TTS research

### ⚠️ Disclaimer
You are responsible for:

Reddit content usage compliance

YouTube monetization rules

Copyright and fair-use policies

This tool does not bypass platform restrictions.

### 📜 License
MIT License.
Use it. Modify it. Break it. Improve it.
