🎬 Reddit-to-YouTube Automation Pipeline

An end-to-end automated pipeline that converts Reddit stories into high-retention YouTube Videos and Shorts using AI voiceovers, dynamic subtitles, and gameplay backgrounds. Fully controllable via Telegram and designed for scale.

🚀 What This Does

This system:

Fetches stories from Reddit automatically

Converts text to natural-sounding AI voiceovers

Generates perfectly time-aligned subtitles

Overlays gameplay footage as background

Renders YouTube Shorts or full videos

Uploads or schedules posting to YouTube

Is controlled remotely via Telegram commands

Zero manual editing.

🧠 Core Features
🔍 Reddit Story Extraction

Fetches stories from selected subreddits

Supports filtering by score, length, and post type

Splits long stories into parts automatically

Stores structured data in JSON

🗣️ AI Voiceover Generation

Uses Bark for expressive text-to-speech

Optional fallback to other TTS engines

Audio normalization and silence trimming

⏱️ Accurate Timestamp Mapping

Uses Whisper word-level timestamps

Maps every spoken word back to original text

Guarantees subtitle sync with audio

No skipped or hallucinated words

📝 Dynamic Subtitle Generation

Generates .ass subtitle files

Shorts: single-word, center-aligned subtitles

Videos: 2–3 word grouped subtitles

Automatic highlighting and emphasis

Timing driven directly by Whisper output

🎮 Gameplay Background Overlay

Supports random or fixed gameplay clips

Auto crop for Shorts (9:16)

Full frame for Videos (16:9)

Syncs video duration to audio length

📤 YouTube Upload & Scheduling

Uses YouTube Data API

Supports:

Auto upload

Scheduled publishing

Title, description, tags automation

Shorts and long-form handled separately

🤖 Telegram Bot Control

Start or stop pipeline remotely

Upload specific story index

Override Shorts vs Video mode

Progress updates and error alerts

No SSH required after setup

🧩 Tech Stack

Language: Python

TTS: Bark

ASR & Alignment: Whisper (word-level timestamps)

Video Processing: FFmpeg

APIs: Reddit API, YouTube Data API, Telegram Bot API

Automation: Cron / Scheduler

Subtitles: ASS (Advanced SubStation Alpha)


⚙️ Setup
1. Clone the repo
git clone https://github.com/yourusername/reddit-to-youtube-pipeline.git
cd reddit-to-youtube-pipeline

2. Install dependencies
pip install -r requirements.txt

3. Configure API keys

Update config.yaml with:

Reddit API credentials

YouTube API credentials

Telegram Bot token

4. Run pipeline
python main_pipeline.py

📌 Telegram Commands (Examples)
/start
/upload 3 short
/upload 5 video
/status
/stop

🧪 Reliability Guarantees

Every word spoken exists in subtitles

Subtitles appear only when audio speaks

Video duration always matches audio

No silent frames

No subtitle drift

If this breaks, your alignment logic is wrong.

📈 Use Cases

Reddit story YouTube channels

Automated Shorts farms

AI narration experiments

Content scaling pipelines

TTS + subtitle research

⚠️ Disclaimer

You are responsible for:

Reddit content usage

YouTube monetization compliance

Copyright and fair-use policies

This tool does not bypass platform rules.

📜 License

MIT License.
Use it. Modify it. Break it. Improve it.
