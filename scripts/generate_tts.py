import os
import sys
import json
import re
import time
import asyncio
import io
import edge_tts
from pydub import AudioSegment

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from scripts.telegram_notify import log

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ====================================================================
# SUBREDDIT-AWARE VOICE MAPPING
# ====================================================================
SUBREDDIT_VOICES = {
    # Casual, funny, thought-provoking
    "askreddit": {
        "male": "en-US-GuyNeural",
        "female": "en-US-MichelleNeural",
        "rate": "+20%"
    },
    # Emotional, serious relationship drama
    "relationship_advice": {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-JennyNeural",
        "rate": "+15%"
    },
    # Dramatic, fast-paced, humorous fuckups
    "tifu": {
        "male": "en-US-EricNeural",
        "female": "en-US-AriaNeural",
        "rate": "+25%"
    },
    # Pop culture & music
    "askredditkpop": {
        "male": "en-US-EricNeural",
        "female": "en-US-AriaNeural",
        "rate": "+20%"
    },
    # Intense drama & payback
    "nuclearrevenge": {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-AriaNeural",
        "rate": "+15%"
    },
    # Moral conflicts & disputes
    "amitheasshole": {
        "male": "en-US-GuyNeural",
        "female": "en-US-JennyNeural",
        "rate": "+15%"
    },
    # Intimate, reflective confessions
    "confessions": {
        "male": "en-US-RogerNeural",
        "female": "en-US-JennyNeural",
        "rate": "+15%"
    },
    # Raw feelings & unfiltered stories
    "trueoffmychest": {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-JennyNeural",
        "rate": "+15%"
    }
}

DEFAULT_VOICE = {
    "male": "en-US-ChristopherNeural",
    "female": "en-US-JennyNeural",
    "rate": "+15%"
}


def get_voice_for_subreddit(subreddit, gender):
    """
    Selects the optimal narrator voice and pacing based on the subreddit and gender.
    Can be overridden if custom values exist in .env.
    """
    sub_key = re.sub(r"^r/", "", subreddit.lower().strip()) if subreddit else ""
    config = SUBREDDIT_VOICES.get(sub_key, DEFAULT_VOICE)

    # Subreddit voice
    voice = config.get(gender, DEFAULT_VOICE[gender])
    rate = config.get("rate", "+15%")

    # Optional manual override via .env if specified
    if gender == "male" and os.getenv("EDGE_VOICE_MALE"):
        voice = os.getenv("EDGE_VOICE_MALE")
    elif gender == "female" and os.getenv("EDGE_VOICE_FEMALE"):
        voice = os.getenv("EDGE_VOICE_FEMALE")

    if os.getenv("EDGE_TTS_RATE"):
        rate = os.getenv("EDGE_TTS_RATE")

    return voice, rate


def detect_gender(text):
    """Detects likely author gender from text markers like '24F', '28M', or pronouns."""
    matches = re.findall(r"\b\d{1,2}[MF]\b", text.upper())
    genders = [m[-1] for m in matches]
    if not genders:
        return "male"
    return "female" if genders.count("F") > genders.count("M") else "male"


def clean_text_for_tts(text):
    """Cleans up typographical punctuation and non-ascii characters for clean TTS."""
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2026", "...")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    return text.strip()


# ====================================================================
# MICROSOFT EDGE-TTS GENERATION WITH WORD-LEVEL TIMESTAMPS
# ====================================================================

async def _tts_edge_async(text, out_wav_path, timing_json_path, voice_name, rate):
    comm = edge_tts.Communicate(text, voice=voice_name, rate=rate, boundary="WordBoundary")
    audio_buffer = bytearray()
    words = []

    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({
                "word": chunk["text"],
                "start": round(chunk["offset"] / 10_000_000, 3),
                "end": round((chunk["offset"] + chunk["duration"]) / 10_000_000, 3)
            })

    # Convert audio stream to clean standard WAV
    seg = AudioSegment.from_file(io.BytesIO(audio_buffer), format="mp3")
    seg.export(out_wav_path, format="wav")

    # Save word-level timestamps for animated subtitles
    with open(timing_json_path, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    return seg.duration_seconds, len(words)


def generate_tts(date_str, story_name):
    """
    Main TTS entrypoint:
    - Reads story JSON
    - Detects gender and selects voice based on subreddit
    - Generates voiceover and word-level timestamps in seconds
    """
    story_folder = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
    audio_dir = os.path.join(PROJECT_ROOT, "audio", date_str)
    os.makedirs(audio_dir, exist_ok=True)

    story_path = os.path.join(story_folder, f"story_{story_name}.json")
    out_path = os.path.join(audio_dir, f"voice_{story_name}.wav")
    timing_path = out_path.replace(".wav", "_timing.json")

    if os.path.exists(out_path) and os.path.exists(timing_path):
        print(f"✅ TTS and timings already exist for story {story_name}, skipping...")
        return out_path

    with open(story_path, "r", encoding="utf-8") as f:
        story = json.load(f)

    full_text = story.get("text", "").strip().replace("\n", " ")
    full_text = clean_text_for_tts(full_text)

    # Detect author gender
    voice_gender = story.get("voice")
    if voice_gender not in ["male", "female"]:
        combined_text = story.get("title", "") + " " + story.get("text", "")
        voice_gender = detect_gender(combined_text)
        story["voice"] = voice_gender
        with open(story_path, "w", encoding="utf-8") as f:
            json.dump(story, f, indent=4, ensure_ascii=False)

    # Select voice based on subreddit & gender
    subreddit = story.get("subreddit", "")
    if not subreddit:
        match = re.match(r"^\[(.*?)\]", story.get("title", ""))
        if match:
            subreddit = match.group(1).strip()

    voice_name, rate = get_voice_for_subreddit(subreddit, voice_gender)

    log(f"🎙️ [Story {story_name}] Subreddit: r/{subreddit} | Gender: {voice_gender} ➔ Voice: {voice_name} (rate: {rate})", telegram=True)

    start_t = time.time()
    duration, word_count = asyncio.run(_tts_edge_async(full_text, out_path, timing_path, voice_name, rate))
    elapsed = time.time() - start_t

    log(f"✅ [Story {story_name}] Voiceover generated: {duration:.1f}s audio ({word_count} words) in {elapsed:.2f}s!", telegram=True)
    return out_path


if __name__ == "__main__":
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    for name in ["1", "2", "3"]:
        generate_tts(date_str, story_name=name)
