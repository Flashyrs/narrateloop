import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

# ====================================================================
# SUBREDDIT-AWARE VOICE MAPPING (Boosted for high viral engagement)
# ====================================================================
SUBREDDIT_VOICES = {
    # Casual, funny, thought-provoking
    "askreddit": {
        "male": "en-US-GuyNeural",
        "female": "en-US-EmmaNeural",
        "rate": "+27%"
    },
    # Emotional, serious relationship drama
    "relationship_advice": {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-JennyNeural",
        "rate": "+25%"
    },
    # Dramatic, fast-paced, humorous fuckups
    "tifu": {
        "male": "en-US-BrianNeural",
        "female": "en-US-AriaNeural",
        "rate": "+27%"
    },
    # Pop culture & music
    "askredditkpop": {
        "male": "en-US-EricNeural",
        "female": "en-US-AriaNeural",
        "rate": "+27%"
    },
    # Moral conflicts, debates
    "amitheasshole": {
        "male": "en-US-GuyNeural",
        "female": "en-US-AriaNeural",
        "rate": "+27%"
    },
    "aitah": {
        "male": "en-US-GuyNeural",
        "female": "en-US-AriaNeural",
        "rate": "+27%"
    },
    # Petty / Pro / Nuclear Revenge
    "pettyrevenge": {
        "male": "en-US-EricNeural",
        "female": "en-US-JennyNeural",
        "rate": "+27%"
    },
    "prorevenge": {
        "male": "en-US-EricNeural",
        "female": "en-US-JennyNeural",
        "rate": "+27%"
    },
    "nuclearrevenge": {
        "male": "en-US-EricNeural",
        "female": "en-US-JennyNeural",
        "rate": "+27%"
    },
    # Intimate, reflective confessions
    "confessions": {
        "male": "en-US-RogerNeural",
        "female": "en-US-JennyNeural",
        "rate": "+25%"
    },
    # Raw feelings & unfiltered stories
    "trueoffmychest": {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-JennyNeural",
        "rate": "+27%"
    },
    "stories": {
        "male": "en-US-AndrewNeural",
        "female": "en-US-AvaNeural",
        "rate": "+27%"
    }
}

DEFAULT_VOICE = {
    "male": "en-US-ChristopherNeural",
    "female": "en-US-JennyNeural",
    "rate": "+27%"
}


def get_voice_for_subreddit(subreddit, gender):
    """
    Selects the optimal narrator voice and pacing based on the subreddit and gender.
    Can be overridden if custom values exist in .env.
    """
    sub_key = re.sub(r"^r/", "", subreddit.lower().strip()) if subreddit else ""
    config = SUBREDDIT_VOICES.get(sub_key, DEFAULT_VOICE)

    # Subreddit voice
    voice = config.get(gender, DEFAULT_VOICE.get(gender, "en-US-ChristopherNeural"))
    rate = config.get("rate", "+27%")

    # Optional manual override via .env if specified
    if gender == "male" and os.getenv("EDGE_VOICE_MALE"):
        voice = os.getenv("EDGE_VOICE_MALE")
    elif gender == "female" and os.getenv("EDGE_VOICE_FEMALE"):
        voice = os.getenv("EDGE_VOICE_FEMALE")

    if os.getenv("EDGE_TTS_RATE"):
        rate = os.getenv("EDGE_TTS_RATE")

    return voice, rate


def detect_gender(text):
    """
    Detects likely narrator gender using contextual NLP analysis:
    - Direct self-identification: 'I (24F)', 'I [28F]', 'as a woman', 'I am a woman/girl/female/wife/mother/mom'
    - Relationship partner context: 'my husband', 'my boyfriend', 'my fiancé', 'my baby daddy' (narrator is female)
    - Inverse male self-identification & partner context: 'I (28M)', 'my wife', 'my girlfriend', 'my fiancée'
    - Age/gender tag parsing with narrator subject association.
    """
    if not text:
        return "male"
    
    text_lower = text.lower()
    
    # 1. Direct female narrator self-identification and female-specific situations
    female_self_patterns = [
        r"\bi\s*[\(\[]\s*\d{1,2}\s*f\s*[\)\]]",
        r"\b\d{1,2}\s*f\b",
        r"\b(i am|i'm|im)\s+(a\s+)?(\d{1,2}\s*(yo|year\s*old)\s+)?(woman|girl|female|wife|mother|mom|bride)\b",
        r"\bas\s+a\s+(\d{1,2}\s*(yo|year\s*old)\s+)?(woman|girl|female|wife|mother|mom)\b",
        r"\b(my\s+husband|my\s+ex-husband|my\s+ex\s+husband|my\s+boyfriend|my\s+ex-boyfriend|my\s+ex\s+bf|my\s+fianc[eé]|my\s+bf|my\s+hubby|my\s+baby\s+daddy)\b",
        r"\bhe\s+called\s+me\s+(his\s+wife|his\s+girl|a\s+bitch|his\s+woman)\b",
        r"\b(pregnant|giving\s+birth|my\s+pregnancy|my\s+period)\b"
    ]
    
    # 2. Direct male narrator self-identification
    male_self_patterns = [
        r"\bi\s*[\(\[]\s*\d{1,2}\s*m\s*[\)\]]",
        r"\b\d{1,2}\s*m\b",
        r"\b(i am|i'm|im)\s+(a\s+)?(\d{1,2}\s*(yo|year\s*old)\s+)?(man|guy|male|husband|father|dad|groom)\b",
        r"\bas\s+a\s+(\d{1,2}\s*(yo|year\s*old)\s+)?(man|guy|male|husband|father|dad)\b",
        r"\b(my\s+wife|my\s+ex-wife|my\s+ex\s+wife|my\s+girlfriend|my\s+ex-girlfriend|my\s+ex\s+gf|my\s+fianc[eé]e|my\s+gf|my\s+baby\s+mama)\b",
        r"\bshe\s+called\s+me\s+(her\s+husband|her\s+man)\b"
    ]
    
    female_score = 0
    male_score = 0
    
    for pat in female_self_patterns:
        female_score += len(re.findall(pat, text_lower)) * 2
        
    for pat in male_self_patterns:
        male_score += len(re.findall(pat, text_lower)) * 2

    # 3. Check standalone age/gender tags: e.g. "husband (41M)" -> husband is male, so speaker is female
    partner_male_tags = re.findall(r"\b(husband|boyfriend|bf|fianc[eé]|ex)\s*[\(\[]\s*\d{1,2}\s*m\s*[\)\]]", text_lower)
    partner_female_tags = re.findall(r"\b(wife|girlfriend|gf|fianc[eé]e|ex)\s*[\(\[]\s*\d{1,2}\s*f\s*[\)\]]", text_lower)
    
    female_score += len(partner_male_tags) * 3
    male_score += len(partner_female_tags) * 3

    if female_score > male_score:
        return "female"
    elif male_score > female_score:
        return "male"

    # Fallback to general isolated gender tags if no contextual relationship match
    general_tags = re.findall(r"\b\d{1,2}([MF])\b", text.upper())
    if general_tags:
        return "female" if general_tags.count("F") > general_tags.count("M") else "male"
        
    return "male"


def clean_text_for_tts(text):
    """Cleans up typographical punctuation, non-ascii characters, URLs, and web links for clean TTS."""
    if not text:
        return ""
    # 1. Strip markdown links: [text](http://...) -> keep text, drop link
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)
    # 2. Strip standard URLs: http://..., https://...
    text = re.sub(r'https?://\S+', '', text)
    # 3. Strip www.... links
    text = re.sub(r'\bwww\.[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=]+', '', text)
    # 4. Strip common reddit link headers like "Original post:", "Source:", "Link:"
    text = re.sub(r'(?i)\b(original\s+post|source\s+link|source|post\s+link|reddit\s+link|link|update)\s*:\s*', '', text)
    # 5. Strip "submitted by...", "posted by...", and "[link] [comments]" metadata
    text = re.sub(r'(?i)\b(submitted\s+by|posted\s+by)\b.*', '', text)
    text = re.sub(r'(?i)\[link\]\s*\[comments\].*', '', text)
    text = re.sub(r'(?i)\b/?u/\w+\b', '', text)
    text = text.replace(r'\_', '_')

    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2026", "...")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    text = re.sub(r'\s+([,.:;?!])', r'\1', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ====================================================================
# MULTI-ROLE DUAL-VOICE SYNTHESIS ENGINE (Google Cloud / Edge-TTS)
# ====================================================================

def _synthesize_google_segment(text, voice_name="en-US-Journey-D", rate_float=1.22):
    """
    Synthesizes text using Google Cloud Text-to-Speech API with high-precision
    sentence-level chunking to ensure word timestamps never drift.
    """
    if not text.strip():
        return AudioSegment.empty(), []

    from google.cloud import texttospeech
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google-tts-key.json")
    if not os.path.isabs(cred_path):
        cred_path = os.path.join(PROJECT_ROOT, cred_path)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

    client = texttospeech.TextToSpeechClient()
    lang_code = "-".join(voice_name.split("-")[:2]) if "-" in voice_name else "en-US"
    voice_params = texttospeech.VoiceSelectionParams(language_code=lang_code, name=voice_name)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=rate_float
    )

    # Split into short sentence/phrase clauses for pinpoint timing accuracy
    sentence_chunks = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    if not sentence_chunks:
        sentence_chunks = [text.strip()]

    combined_audio = AudioSegment.empty()
    all_words = []
    current_time = 0.0

    for chunk in sentence_chunks:
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        response = client.synthesize_speech(input=synthesis_input, voice=voice_params, audio_config=audio_config)
        seg = AudioSegment.from_file(io.BytesIO(response.audio_content), format="wav")

        words_raw = chunk.split()
        if not words_raw:
            continue
            
        total_chars = max(1, sum(len(w) for w in words_raw))
        chunk_sec = seg.duration_seconds

        for w in words_raw:
            w_dur = (len(w) / total_chars) * chunk_sec
            all_words.append({
                "word": w,
                "start": round(current_time, 3),
                "end": round(current_time + w_dur, 3)
            })
            current_time += w_dur

        combined_audio += seg
        current_time = combined_audio.duration_seconds

    return combined_audio, all_words

def normalize_segment_loudness(seg, target_dBFS=-16.0):
    """Normalizes an AudioSegment to a consistent target dBFS to ensure all characters have uniform volume."""
    if len(seg) == 0 or seg.dBFS == float('-inf'):
        return seg
    gain = target_dBFS - seg.dBFS
    # Clamp gain within [-12, +12] dB to prevent distortion or blowing out noise floors
    gain = max(-12.0, min(12.0, gain))
    return seg.apply_gain(gain)

async def _synthesize_edge_segment(text, voice_name, rate="+25%"):
    """Synthesizes an individual text chunk via Edge-TTS and returns (AudioSegment, word_timings_list)."""
    if not text.strip():
        return AudioSegment.empty(), []

    comm = edge_tts.Communicate(text.strip(), voice=voice_name, rate=rate, boundary="WordBoundary")
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

    if not audio_buffer:
        return AudioSegment.empty(), []

    seg = AudioSegment.from_file(io.BytesIO(audio_buffer), format="mp3")
    return seg, words


async def _tts_dual_role_async(story_dict, out_wav_path, timing_json_path, narrator_voice, host_voice, rate):
    """
    Synthesizes a 4-part multi-speaker video track with Google Cloud TTS (or Edge-TTS fallback):
    1. Hook (Host Voice)
    2. Story (Narrator Voice - gender matched)
    3. Analysis (Host Voice - thoughtful pacing)
    4. Debate Question (Host Voice)
    """
    hook_text = clean_text_for_tts(story_dict.get("hook", ""))
    story_text = clean_text_for_tts(story_dict.get("story", story_dict.get("text", "")))
    analysis_text = clean_text_for_tts(story_dict.get("analysis", ""))
    debate_text = clean_text_for_tts(story_dict.get("debate_question", ""))
    
    raw_title = story_dict.get("title", "")
    clean_title = re.sub(r"^\[.*?\]\s*", "", raw_title)
    clean_title = clean_text_for_tts(clean_title)

    engine = os.getenv("TTS_ENGINE", "google").lower()
    cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google-tts-key.json")
    if not os.path.isabs(cred_file):
        cred_file = os.path.join(PROJECT_ROOT, cred_file)
    use_google = (engine == "google" and os.path.exists(cred_file))

    # Google Cloud Voice Mappings
    google_host_voice = os.getenv("GOOGLE_TTS_HOST_VOICE", "en-US-Journey-D")
    narrator_gender = story_dict.get("voice", "male")
    if narrator_gender == "female":
        google_narrator_voice = os.getenv("GOOGLE_TTS_FEMALE_VOICE", "en-US-Journey-F")
    else:
        google_narrator_voice = os.getenv("GOOGLE_TTS_MALE_VOICE", "en-US-Neural2-J")

    # Check if this is a Conversation Short (Slot 1) with structured chat messages
    is_conv_short = (story_dict.get("story_format") == "message_short" and bool(story_dict.get("chat_messages")))
    message_timings = []

    if is_conv_short:
        # Context-aware Contact & Narrator Gender Detection
        contact_name = story_dict.get("contact_name", "Messages")
        c_lower = contact_name.lower()
        male_contact_indicators = ["mark", "dave", "david", "john", "mike", "dan", "charles", "husband", "landlord", "boss", "dad", "father", "brother", "fiance", "fiancé", "groom", "ex-husband"]
        female_contact_indicators = ["sarah", "emily", "karen", "jessica", "wife", "mom", "mother", "sister", "bride", "fiancee", "fiancée", "bridezilla", "ex-wife"]

        if any(w in c_lower for w in male_contact_indicators):
            contact_gender = "male"
            me_gender = "female"
        elif any(w in c_lower for w in female_contact_indicators):
            contact_gender = "female"
            me_gender = "male"
        else:
            me_gender = story_dict.get("voice", "female")
            contact_gender = "male" if me_gender == "female" else "female"

        # Edge-TTS Voice mappings
        contact_edge = "en-US-GuyNeural" if contact_gender == "male" else "en-US-JennyNeural"
        me_edge = "en-US-JennyNeural" if me_gender == "female" else "en-US-GuyNeural"

        # Google Cloud Voice mappings
        contact_google = "en-US-Neural2-J" if contact_gender == "male" else "en-US-Journey-F"
        me_google = "en-US-Journey-F" if me_gender == "female" else "en-US-Neural2-J"

        # 1. Intro Hook (spoken once by Host Voice)
        segments_to_build = []
        if hook_text:
            intro_content = f"{clean_title}. {hook_text}" if (clean_title and clean_title.lower() not in hook_text.lower()) else (hook_text or clean_title)
            segments_to_build.append(("hook", intro_content, host_voice, google_host_voice, "+25%", 1.25, -1))
        elif clean_title:
            segments_to_build.append(("hook", clean_title, host_voice, google_host_voice, "+25%", 1.25, -1))

        # 2. Individual dialogue messages (Natural, tense dramatic pacing)
        for m_idx, m in enumerate(story_dict["chat_messages"]):
            m_text = clean_text_for_tts(m.get("text", ""))
            if not m_text:
                continue
            is_me = m.get("is_me", False) or m.get("sender", "").lower() in ["me", "op", "i"]
            if is_me:
                segments_to_build.append(("msg_me", m_text, me_edge, me_google, "+6%", 1.06, m_idx))
            else:
                segments_to_build.append(("msg_contact", m_text, contact_edge, contact_google, "+6%", 1.06, m_idx))

        # 3. Closing CTA
        if debate_text:
            segments_to_build.append(("debate", debate_text, host_voice, google_host_voice, "+15%", 1.15, -1))
    else:
        # Standard Multi-Role Flow (Slots 2 & 3)
        segments_to_build = []
        
        # 1. Intro / Hook
        if hook_text:
            intro_content = f"{clean_title}. {hook_text}" if (clean_title and clean_title.lower() not in hook_text.lower()) else (hook_text or clean_title)
            segments_to_build.append(("hook", intro_content, host_voice, google_host_voice, "+15%", 1.15, -1))
        elif clean_title:
            segments_to_build.append(("hook", clean_title, host_voice, google_host_voice, "+15%", 1.15, -1))

        # 2. Main Story Body
        if story_text:
            segments_to_build.append(("story", story_text, narrator_voice, google_narrator_voice, "+14%", 1.14, -1))

        # 3. Host Critical Analysis
        if analysis_text:
            segments_to_build.append(("analysis", analysis_text, host_voice, google_host_voice, "+12%", 1.12, -1))

        # 4. Closing Debate Question
        if debate_text:
            segments_to_build.append(("debate", debate_text, host_voice, google_host_voice, "+15%", 1.15, -1))

    master_audio = AudioSegment.empty()
    all_words = []
    milestones = {
        "title_end_time": 3.0,
        "story_end_time": 0.0,
        "analysis_start_time": 0.0,
        "analysis_end_time": 0.0
    }

    current_offset = 0.0
    gap = AudioSegment.silent(duration=180)  # 180ms natural pause between speakers

    for item in segments_to_build:
        role = item[0]
        text = item[1]
        e_vname = item[2]
        g_vname = item[3]
        e_rate = item[4]
        g_rate = item[5]
        m_idx = item[6] if len(item) > 6 else -1

        if not text:
            continue

        seg, words = AudioSegment.empty(), []

        if use_google:
            try:
                seg, words = _synthesize_google_segment(text, voice_name=g_vname, rate_float=g_rate)
            except Exception as ge:
                print(f"⚠️ Google Cloud TTS warning for segment {role} ({ge}) ➔ Falling back to Edge-TTS")
                seg, words = await _synthesize_edge_segment(text, e_vname, e_rate)
        else:
            seg, words = await _synthesize_edge_segment(text, e_vname, e_rate)

        if len(seg) == 0:
            continue

        # Ensure consistent perceived loudness across all voice roles
        seg = normalize_segment_loudness(seg, target_dBFS=-16.0)

        seg_start = round(current_offset, 3)
        seg_dur = len(seg) / 1000.0
        seg_end = round(seg_start + seg_dur, 3)

        if role == "analysis":
            milestones["analysis_start_time"] = seg_start
        elif role in ["msg_me", "msg_contact"] and m_idx >= 0:
            message_timings.append({
                "msg_idx": m_idx,
                "start": seg_start,
                "end": seg_end,
                "role": role,
                "text": text
            })

        # Shift word timestamps by current global audio offset
        for w in words:
            all_words.append({
                "word": w["word"],
                "start": round(w["start"] + current_offset, 3),
                "end": round(w["end"] + current_offset, 3),
                "role": role
            })

        master_audio += seg + gap
        current_offset += (len(seg) + len(gap)) / 1000.0

        if role == "hook":
            milestones["title_end_time"] = round(current_offset - (len(gap) / 1000.0), 3)
        elif role == "story":
            milestones["story_end_time"] = round(current_offset - (len(gap) / 1000.0), 3)
        elif role == "analysis":
            milestones["analysis_end_time"] = round(current_offset - (len(gap) / 1000.0), 3)

    # Add natural 1.2s end padding so video never ends abruptly
    end_pad = AudioSegment.silent(duration=1200)
    master_audio += end_pad

    # Peak normalize master audio for clean broadcast headroom
    try:
        from pydub.effects import normalize as pydub_normalize
        master_audio = pydub_normalize(master_audio, headroom=1.0)
    except Exception:
        pass

    # Export master WAV
    master_audio.export(out_wav_path, format="wav")

    timing_payload = {
        "title_end_time": milestones["title_end_time"],
        "story_end_time": milestones["story_end_time"],
        "analysis_start_time": milestones["analysis_start_time"],
        "analysis_end_time": milestones["analysis_end_time"],
        "clean_title": clean_title,
        "message_timings": message_timings,
        "words": all_words
    }

    with open(timing_json_path, "w", encoding="utf-8") as f:
        json.dump(timing_payload, f, ensure_ascii=False, indent=2)

    return master_audio.duration_seconds, len(all_words)



def generate_tts(date_str, story_name):
    """
    Main TTS entrypoint:
    - Reads story JSON
    - Assigns Host Voice (Authority/Commentary) and Narrator Voice (Gender-matched)
    - Synthesizes dual-role audio track with word timings
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

    # Detect author gender for narrator voice
    voice_gender = story.get("voice")
    if voice_gender not in ["male", "female"]:
        combined_text = story.get("title", "") + " " + story.get("text", "")
        voice_gender = detect_gender(combined_text)
        story["voice"] = voice_gender
        with open(story_path, "w", encoding="utf-8") as f:
            json.dump(story, f, indent=4, ensure_ascii=False)

    # Select narrator voice based on subreddit & gender
    subreddit = story.get("subreddit", "")
    if not subreddit:
        match = re.match(r"^\[(.*?)\]", story.get("title", ""))
        if match:
            subreddit = match.group(1).strip()

    narrator_voice, rate = get_voice_for_subreddit(subreddit, voice_gender)
    
    # Host voice for Commentary/Analysis/Hook (Confident, authoritative podcaster voice)
    host_voice = os.getenv("HOST_VOICE", "en-US-GuyNeural")
    if narrator_voice == host_voice and voice_gender == "male":
        narrator_voice = "en-US-ChristopherNeural"

    engine = os.getenv("TTS_ENGINE", "google").lower()
    cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google-tts-key.json")
    if not os.path.isabs(cred_file):
        cred_file = os.path.join(PROJECT_ROOT, cred_file)
    use_google = (engine == "google" and os.path.exists(cred_file))

    if use_google:
        host_disp = os.getenv("GOOGLE_TTS_HOST_VOICE", "en-US-Journey-D")
        narr_disp = os.getenv("GOOGLE_TTS_FEMALE_VOICE", "en-US-Journey-F") if voice_gender == "female" else os.getenv("GOOGLE_TTS_MALE_VOICE", "en-US-Neural2-J")
        engine_label = "Google Cloud TTS (Journey/Neural2)"
    else:
        host_disp = host_voice
        narr_disp = narrator_voice
        engine_label = "Edge-TTS"

    log(f"🎙️ [{engine_label}] [Story {story_name}] Host: {host_disp} | Narrator: {narr_disp} ({voice_gender}) | Subreddit: r/{subreddit}", telegram=True)

    start_t = time.time()
    duration, word_count = asyncio.run(_tts_dual_role_async(
        story, out_path, timing_path,
        narrator_voice=narrator_voice,
        host_voice=host_voice,
        rate=rate
    ))
    elapsed = time.time() - start_t

    log(f"✅ [Story {story_name}] Dual-voice audio generated: {duration:.1f}s ({word_count} words) in {elapsed:.2f}s!", telegram=True)
    return out_path


if __name__ == "__main__":
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    target_names = ["1", "2", "3"]
    if len(sys.argv) > 1 and sys.argv[1].isdigit() and len(sys.argv[1]) == 8:
        date_str = sys.argv[1]
    if len(sys.argv) > 2:
        target_names = [sys.argv[2]]
    for name in target_names:
        generate_tts(date_str, story_name=name)

