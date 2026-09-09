import os
import sys
import datetime
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import random
import subprocess
import wave
import tempfile
import math
from pathlib import Path
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

def mix_voice_and_sfx(voice_wav_path, sfx_events, output_wav_path):
    """
    Overlays all sound effects (whooshes, pops, chimes) directly onto the voice audio
    using pydub with exact millisecond precision.
    Guarantees 100% constant voice volume without FFmpeg amix re-weighting or volume ramp bugs.
    """
    if not os.path.exists(voice_wav_path):
        return voice_wav_path
    try:
        voice_audio = AudioSegment.from_file(voice_wav_path).set_frame_rate(44100).set_channels(2)
        for sfx_path, start_sec, vol_mult in sfx_events:
            if not sfx_path or not os.path.exists(sfx_path):
                continue
            try:
                sfx = AudioSegment.from_file(sfx_path).set_frame_rate(44100).set_channels(2)
                gain_db = 20.0 * math.log10(max(0.01, float(vol_mult)))
                sfx = sfx.apply_gain(gain_db)
                pos_ms = max(0, int(float(start_sec) * 1000))
                voice_audio = voice_audio.overlay(sfx, position=pos_ms)
            except Exception as se:
                print(f"⚠️ Warning overlaying SFX ({sfx_path}): {se}")
        os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
        voice_audio.export(output_wav_path, format="wav")
        return output_wav_path
    except Exception as e:
        print(f"⚠️ SFX mixing fallback ({e}), using original voice audio.")
        return voice_wav_path


GAMEPLAY_DIR = os.path.join(PROJECT_ROOT, "assets", "gameplays")
MUSIC_DIR = os.path.join(PROJECT_ROOT, "assets", "music")
SFX_DIR = os.path.join(PROJECT_ROOT, "assets", "sfx")

_video_duration_cache = {}

SUBREDDIT_MOOD_MAP = {
    "NuclearRevenge": "suspense",
    "ProRevenge": "suspense",
    "confessions": "suspense",
    "AITAH": "suspense",
    "AmItheAsshole": "suspense",
    "relationship_advice": "emotional",
    "TrueOffMyChest": "emotional",
    "offmychest": "emotional",
    "Stories": "emotional",
    "pettyrevenge": "chill",
    "tifu": "chill",
    "entitledparents": "chill",
    "EntitledPeople": "chill",
    "maliciouscompliance": "chill",
    "AskReddit": "chill"
}

def detect_story_mood(subreddit="", text=""):
    """
    Detects the optimal background music mood ('suspense', 'emotional', or 'chill')
    based on story context and subreddit.
    """
    text_lower = text.lower() if text else ""
    
    # 1. High-priority keyword signals
    if any(w in text_lower for w in ["cheated", "cheating", "revenge", "caught", "police", "lawyer", "lawsuit", "arrested", "secret affair", "betrayed", "unfaithful"]):
        return "suspense"
    if any(w in text_lower for w in ["crying", "heartbroken", "divorce", "passed away", "passed on", "grief", "brokenhearted", "lost my"]):
        return "emotional"
    if any(w in text_lower for w in ["karen", "petty", "laughed", "boss", "coworker", "embarrassing", "stupid"]):
        return "chill"
        
    # 2. Subreddit default mood mapping
    if subreddit in SUBREDDIT_MOOD_MAP:
        return SUBREDDIT_MOOD_MAP[subreddit]
        
    return "chill"

def get_available_music_tracks():
    """Returns a list of all valid audio tracks in assets/music."""
    valid_exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    if not os.path.exists(MUSIC_DIR):
        os.makedirs(MUSIC_DIR, exist_ok=True)
    return [
        os.path.join(MUSIC_DIR, f)
        for f in os.listdir(MUSIC_DIR)
        if Path(f).suffix.lower() in valid_exts and not f.startswith(".")
    ]

def get_content_aware_music(subreddit="", text=""):
    """
    Selects the best matching music track from assets/music/ based on story mood.
    Falls back gracefully to any available track.
    """
    all_tracks = get_available_music_tracks()
    if not all_tracks:
        return None
        
    mood = detect_story_mood(subreddit, text)
    mood_tracks = [t for t in all_tracks if os.path.basename(t).lower().startswith(mood)]
    
    if mood_tracks:
        chosen = random.choice(mood_tracks)
        print(f"[DEBUG] [Content-Aware Audio] Matched mood [{mood.upper()}]: {os.path.basename(chosen)}")
        return chosen
        
    # Fallback to random choice from all tracks
    chosen = random.choice(all_tracks)
    print(f"[DEBUG] [Content-Aware Audio] Default track selected: {os.path.basename(chosen)}")
    return chosen


def get_audio_duration(audio_path):
    """Accurately gets audio duration in seconds using wave or ffprobe."""
    try:
        with wave.open(audio_path, 'rb') as f:
            frames = f.getnframes()
            rate = f.getframerate()
            return frames / float(rate)
    except Exception:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            out = subprocess.check_output(cmd, text=True).strip()
            return float(out)
        except Exception:
            return 60.0  # Fallback duration estimate


def get_video_duration(video_path):
    """Gets video duration using ffprobe with in-memory caching."""
    video_path_str = str(video_path)
    if video_path_str in _video_duration_cache:
        return _video_duration_cache[video_path_str]

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path_str
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        dur = float(out)
        _video_duration_cache[video_path_str] = dur
        return dur
    except Exception:
        # Default fallback estimate if ffprobe fails on a clip
        return 7.0


def get_available_gameplay_clips():
    """Returns a list of all valid video clips in assets/gameplays."""
    valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    if not os.path.exists(GAMEPLAY_DIR):
        os.makedirs(GAMEPLAY_DIR, exist_ok=True)

    clips = [
        os.path.join(GAMEPLAY_DIR, f)
        for f in os.listdir(GAMEPLAY_DIR)
        if Path(f).suffix.lower() in valid_exts and not f.startswith(".")
    ]
    return clips


def prepare_gameplay_input(audio_duration, specific_clip_path=None):
    """
    Prepares gameplay video inputs using either:
    - Method A (single offset): Random start timestamp from a long video
    - Method B (montage): Dynamic multi-clip slices stitched seamlessly via concat filter (for YPP)
    """
    all_clips = get_available_gameplay_clips()

    if not all_clips and (not specific_clip_path or not os.path.exists(specific_clip_path)):
        raise FileNotFoundError(f"[ERROR] No gameplay video clips found in {GAMEPLAY_DIR}")

    # Boolean toggle: ENABLE_MONTAGE (defaults to true for YPP compliance)
    enable_montage = os.getenv("ENABLE_MONTAGE", "true").strip().lower() in ("true", "1", "yes")
    if not enable_montage and os.getenv("GAMEPLAY_MODE", "").strip().lower() == "montage":
        enable_montage = True

    target_duration = audio_duration + 5.0  # 5 second buffer for safety

    # ----------------------------------------------------
    # METHOD A: Single Clip Random Offset (only when montage is explicitly disabled)
    # ----------------------------------------------------
    if not enable_montage:
        candidate_clip = specific_clip_path if (specific_clip_path and os.path.exists(specific_clip_path)) else random.choice(all_clips)
        clip_dur = get_video_duration(candidate_clip)
        max_start = max(0.0, clip_dur - target_duration)
        start_offset = random.uniform(0.0, max_start)
        print(f"[DEBUG] [Method A - Single Clip] Chosen: {os.path.basename(candidate_clip)} (Length: {clip_dur:.1f}s) starting at {start_offset:.1f}s, duration: {target_duration:.1f}s")
        return [
            "-ss", f"{start_offset:.2f}",
            "-t", f"{target_duration:.2f}",
            "-avoid_negative_ts", "make_zero",
            "-i", candidate_clip.replace("\\", "/")
        ], 1

    # ----------------------------------------------------
    # METHOD B: Multi-Input Filter-Graph Montage (100% Stable, No Black Screens)
    # ----------------------------------------------------
    print(f"[DEBUG] [Method B - YPP Montage] Slicing dynamic 9-14s scenes across gameplay clips...")
    selected_slices = []
    accumulated_duration = 0.0
    pool = list(all_clips) if all_clips else ([specific_clip_path] if specific_clip_path else [])
    random.shuffle(pool)

    # If a specific starting clip is preferred, place it at the front of the montage pool
    if specific_clip_path and os.path.exists(specific_clip_path) and specific_clip_path in pool:
        pool.remove(specific_clip_path)
        pool.insert(0, specific_clip_path)

    while accumulated_duration < target_duration and pool:
        clip = pool.pop(0)
        dur = get_video_duration(clip)

        slice_len = min(dur, random.uniform(9.0, 14.0))
        max_start = max(0.0, dur - slice_len)
        start_pt = random.uniform(0.0, max_start)

        selected_slices.append((clip, start_pt, slice_len))
        accumulated_duration += slice_len

        if not pool:
            pool = list(all_clips)
            random.shuffle(pool)

    print(f"[DEBUG] Assembled {len(selected_slices)} dynamic video cuts (total ~{accumulated_duration:.1f}s)")

    input_args = []
    for clip_path, in_pt, slice_len in selected_slices:
        input_args.extend([
            "-ss", f"{in_pt:.2f}",
            "-t", f"{slice_len:.2f}",
            "-avoid_negative_ts", "make_zero",
            "-i", clip_path.replace("\\", "/")
        ])

    return input_args, len(selected_slices)


_detected_encoder = None
def get_best_video_encoder():
    global _detected_encoder
    if _detected_encoder is not None:
        return _detected_encoder

    custom = os.getenv("VIDEO_ENCODER")
    if custom:
        _detected_encoder = custom
        return _detected_encoder

    # Check if NVIDIA hardware acceleration (h264_nvenc) is available
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if res.returncode == 0:
            _detected_encoder = "h264_nvenc"
            return _detected_encoder
    except Exception:
        pass

    _detected_encoder = "libx264"
    return _detected_encoder


from utils.badge_utils import create_breakdown_badge

def get_sfx_file(category="whoosh"):
    """Finds a valid audio file in assets/sfx matching the given category (whoosh, pop, chime, click)."""
    if not os.path.exists(SFX_DIR):
        return None
    files = [f for f in os.listdir(SFX_DIR) if not f.startswith(".")]
    matches = [
        os.path.join(SFX_DIR, f) for f in files
        if category.lower() in f.lower() and Path(f).suffix.lower() in {".wav", ".mp3", ".ogg"}
    ]
    if matches:
        return random.choice(matches)
    # Fallback to any sfx if specific category missing
    all_sfx = [os.path.join(SFX_DIR, f) for f in files if Path(f).suffix.lower() in {".wav", ".mp3", ".ogg"}]
    return random.choice(all_sfx) if all_sfx else None

def render_video(date_str, gameplay_path=None, story_name=1, format="short"):
    print(f"[DEBUG] Starting render_video for story: {story_name} on date: {date_str}, format: {format}")

    audio_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"audio/{date_str}/voice_{story_name}.wav"))
    subtitle_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"subtitles/{date_str}_{story_name}_{format}.ass"))
    output_dir = os.path.join(PROJECT_ROOT, f"output/{date_str}")
    output_path = os.path.abspath(os.path.join(output_dir, f"final_{story_name}.mp4"))

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"[ERROR] Audio file not found: {audio_path}")
    if not os.path.exists(subtitle_path):
        raise FileNotFoundError(f"[ERROR] Subtitle file not found: {subtitle_path}")

    audio_duration = get_audio_duration(audio_path)
    print(f"[DEBUG] Audio duration: {audio_duration:.2f}s")

    # Prepare gameplay video inputs (Method A single or Method B montage)
    gameplay_input_args, num_gameplay_inputs = prepare_gameplay_input(audio_duration, specific_clip_path=gameplay_path)

    # Check if transparent card overlay exists for live gameplay video intro
    card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/card_{story_name}.png"))
    thumb_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/thumb_{story_name}.png"))
    
    overlay_img_path = None
    if os.path.exists(card_path):
        overlay_img_path = card_path
    elif os.path.exists(thumb_path):
        overlay_img_path = thumb_path

    # Read title duration & analysis milestones from timing JSON
    timing_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"audio/{date_str}/voice_{story_name}_timing.json"))
    title_end_time = 3.0
    analysis_start_time = 0.0
    analysis_end_time = 0.0
    if os.path.exists(timing_path):
        try:
            with open(timing_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                if isinstance(tdata, dict):
                    title_end_time = float(tdata.get("title_end_time", 3.0))
                    analysis_start_time = float(tdata.get("analysis_start_time", 0.0))
                    analysis_end_time = float(tdata.get("analysis_end_time", 0.0))
        except Exception:
            pass

    # Read story JSON for content-aware audio and subtitle matching
    story_json_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/story_{story_name}.json"))
    story_subreddit = ""
    story_text = ""
    if os.path.exists(story_json_path):
        try:
            with open(story_json_path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
                if isinstance(sdata, dict):
                    story_subreddit = sdata.get("subreddit", "")
                    story_text = sdata.get("text", "")
        except Exception:
            pass

    def ffmpeg_path(path):
        return path.replace("\\", "/").replace(":", "\\:")

    audio_path_ffmpeg = audio_path.replace("\\", "/")
    subtitle_path_ffmpeg = ffmpeg_path(subtitle_path)

    w, h = (1080, 1920) if format == "short" else (1920, 1080)

    encoder = get_best_video_encoder()
    print(f"[DEBUG] Using video encoder: {encoder}")

    # Build FFmpeg inputs:
    # Inputs 0..num_gameplay_inputs-1: gameplay video slices
    input_args = list(gameplay_input_args)
    current_input_idx = num_gameplay_inputs

    # Input (optional): Title card overlay image
    card_idx = None
    if overlay_img_path:
        card_idx = current_input_idx
        current_input_idx += 1
        overlay_path_ffmpeg = overlay_img_path.replace("\\", "/")
        input_args += ["-loop", "1", "-t", f"{title_end_time + 2.0:.2f}", "-i", overlay_path_ffmpeg]

    # Input (optional): Progressive Message Steps or Paged Chat Conversation Overlays
    paged_chat_streams = []
    
    # 1. Check if step-by-step progressive animation cards exist
    step_entries = []
    step_k = 0
    while True:
        step_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/chat_{story_name}_step_{step_k}.png"))
        if os.path.exists(step_card_path):
            step_entries.append(step_card_path)
            step_k += 1
        else:
            break

    # Read message_timings from timing JSON if available
    msg_timings = []
    if os.path.exists(timing_path):
        try:
            with open(timing_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                if isinstance(tdata, dict):
                    msg_timings = tdata.get("message_timings", [])
        except Exception:
            pass

    if step_entries and msg_timings and len(msg_timings) == len(step_entries):
        for s_i, s_path in enumerate(step_entries):
            s_idx = current_input_idx
            current_input_idx += 1
            input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", s_path.replace("\\", "/")]
            m_start = float(msg_timings[s_i]["start"])
            m_end = float(msg_timings[s_i+1]["start"]) if (s_i + 1 < len(msg_timings)) else (audio_duration - 1.0)
            paged_chat_streams.append((s_idx, m_start, m_end, (s_i % 3 == 0)))
    elif step_entries:
        conv_duration = max(1.0, audio_duration - title_end_time - 2.0)
        step_dur = conv_duration / float(len(step_entries))
        for s_i, s_path in enumerate(step_entries):
            s_idx = current_input_idx
            current_input_idx += 1
            input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", s_path.replace("\\", "/")]
            s_st = title_end_time + s_i * step_dur
            s_et = title_end_time + (s_i + 1) * step_dur
            paged_chat_streams.append((s_idx, s_st, s_et, (s_i % 3 == 0)))
    else:
        # Fallback to discrete paged cards
        paged_chat_entries = []
        p_num = 0
        while True:
            p_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/chat_{story_name}_p{p_num}.png"))
            if os.path.exists(p_card_path):
                paged_chat_entries.append(p_card_path)
                p_num += 1
            else:
                break
        if paged_chat_entries:
            num_pages = len(paged_chat_entries)
            conv_duration = max(1.0, audio_duration - title_end_time)
            page_dur = conv_duration / float(num_pages)
            for p_i, p_path in enumerate(paged_chat_entries):
                p_idx = current_input_idx
                current_input_idx += 1
                input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", p_path.replace("\\", "/")]
                p_st = title_end_time + p_i * page_dur
                p_et = title_end_time + (p_i + 1) * page_dur
                paged_chat_streams.append((p_idx, p_st, p_et, True))
        else:
            # Fallback to single chat overlay if paged cards not present
            chat_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/chat_{story_name}.png"))
            chat_start = title_end_time
            chat_end = min(analysis_start_time - 3.0, title_end_time + 14.0) if analysis_start_time > 0 else (title_end_time + 12.0)
            if os.path.exists(chat_card_path) and chat_end > chat_start + 2.0:
                c_idx = current_input_idx
                current_input_idx += 1
                input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", chat_card_path.replace("\\", "/")]
                paged_chat_streams.append((c_idx, chat_start, chat_end, True))

    # Input (optional): Pivotal Quote Card Overlay (Slot 2)
    quote_idx = None
    quote_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/quote_{story_name}.png"))
    quote_start = max(title_end_time + 6.0, analysis_start_time - 6.5) if analysis_start_time > 0 else (title_end_time + 8.0)
    quote_end = analysis_start_time if analysis_start_time > 0 else (quote_start + 6.0)
    if os.path.exists(quote_card_path) and quote_end > quote_start + 1.5:
        quote_idx = current_input_idx
        current_input_idx += 1
        input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", quote_card_path.replace("\\", "/")]

    # Input (optional): Psychological Red Flags Analysis Card Overlay (Slot 2)
    analysis_card_idx = None
    analysis_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/analysis_card_{story_name}.png"))
    ac_start = analysis_start_time
    ac_end = min(analysis_start_time + 7.5, analysis_end_time) if analysis_end_time > 0 else (analysis_start_time + 7.0)
    if os.path.exists(analysis_card_path) and ac_end > ac_start + 2.0:
        analysis_card_idx = current_input_idx
        current_input_idx += 1
        input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", analysis_card_path.replace("\\", "/")]

    # Input (optional): Community Verdict Card Overlay (Slot 3)
    verdict_idx = None
    verdict_card_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/verdict_{story_name}.png"))
    v_start = title_end_time + max(4.0, (audio_duration - title_end_time) * 0.35)
    v_end = audio_duration - 0.8
    if os.path.exists(verdict_card_path) and v_end > v_start + 2.0:
        verdict_idx = current_input_idx
        current_input_idx += 1
        input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", verdict_card_path.replace("\\", "/")]

    # Input (optional): Premium Breakdown Graphic Badge
    badge_idx = None
    if analysis_start_time > 0 and analysis_end_time > analysis_start_time:
        badge_path = os.path.join(PROJECT_ROOT, "assets", "breakdown_badge.png")
        if not os.path.exists(badge_path):
            try:
                create_breakdown_badge(badge_path)
            except Exception:
                pass
        if os.path.exists(badge_path):
            badge_idx = current_input_idx
            current_input_idx += 1
            badge_path_ffmpeg = badge_path.replace("\\", "/")
            input_args += ["-loop", "1", "-t", f"{audio_duration + 2.0:.2f}", "-i", badge_path_ffmpeg]

    # Collect SFX events for seamless millisecond-precise pre-mixing
    sfx_events = []
    
    # 1. Card exit whoosh SFX
    whoosh_file = get_sfx_file("whoosh")
    if card_idx is not None and whoosh_file and os.path.exists(whoosh_file):
        sfx_events.append((whoosh_file, max(0.0, title_end_time - 0.3), 0.35))

    # 2. Paged Chat Pops SFX
    pop_file = get_sfx_file("pop")
    if paged_chat_streams and pop_file and os.path.exists(pop_file):
        for stream_item in paged_chat_streams:
            p_st = stream_item[1]
            sfx_events.append((pop_file, p_st, 0.30))

    # 3. Breakdown Badge Pop SFX
    if badge_idx is not None and pop_file and os.path.exists(pop_file):
        sfx_events.append((pop_file, max(0.0, analysis_start_time), 0.40))

    # 4. Community Verdict Chime SFX
    chime_file = get_sfx_file("chimes") or get_sfx_file("click") or pop_file
    if verdict_idx is not None and chime_file and os.path.exists(chime_file):
        sfx_events.append((chime_file, max(0.0, v_start), 0.35))

    # 5. Debate CTA Attention Chime / Click SFX
    if analysis_end_time > 0 and chime_file and os.path.exists(chime_file):
        sfx_events.append((chime_file, max(0.0, analysis_end_time), 0.25))

    # Pre-mix voice and all SFX with pydub (guarantees rock-solid uniform voice loudness)
    temp_mixed_voice_path = os.path.join(PROJECT_ROOT, "scratch", f"mixed_voice_{date_str}_{story_name}.wav")
    final_voice_path = mix_voice_and_sfx(audio_path, sfx_events, temp_mixed_voice_path)
    
    # Add final mixed voice audio track to FFmpeg inputs
    voice_idx = current_input_idx
    current_input_idx += 1
    input_args += ["-i", final_voice_path.replace("\\", "/")]

    # Input (optional): Background music track (Content-Aware Selection)
    chosen_music = get_content_aware_music(subreddit=story_subreddit, text=story_text)
    music_idx = None
    if chosen_music:
        music_idx = current_input_idx
        current_input_idx += 1
        input_args += ["-stream_loop", "10", "-t", f"{audio_duration + 2.0:.2f}", "-i", chosen_music.replace("\\", "/")]
        print(f"[DEBUG] Layering background music: {os.path.basename(chosen_music)}")

    # ----------------------------------------------------
    # Video Filter Graph Construction (Multi-Input Concat + Overlays + Subs)
    # ----------------------------------------------------
    v_filters = []
    if num_gameplay_inputs == 1:
        v_filters.append(f"[0:v]fps=30,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,setpts=PTS-STARTPTS[gameplay]")
    else:
        slice_labels = []
        for k in range(num_gameplay_inputs):
            v_filters.append(f"[{k}:v]fps=30,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,setpts=PTS-STARTPTS[v_sl_{k}]")
            slice_labels.append(f"[v_sl_{k}]")
        v_filters.append(f"{''.join(slice_labels)}concat=n={num_gameplay_inputs}:v=1:a=0[gameplay]")

    # Card Overlay (Title Intro)
    if card_idx is not None:
        fade_d = 0.35
        fade_st = max(0.1, title_end_time - fade_d)
        v_filters.append(
            f"[{card_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,fade=t=out:st={fade_st:.2f}:d={fade_d:.2f}:alpha=1[card]"
        )
        v_filters.append(
            f"[gameplay][card]overlay=0:0:enable='between(t,0,{title_end_time:.2f})':eof_action=pass[v_merged]"
        )
        base_v_stream = "[v_merged]"
    else:
        base_v_stream = "[gameplay]"

    # Progressive Step-by-Step Message / Paged Chat Conversation Overlays
    for stream_item in paged_chat_streams:
        p_idx, p_st, p_et = stream_item[0], stream_item[1], stream_item[2]
        v_out_label = f"v_with_pg_{p_idx}"
        v_filters.append(
            f"{base_v_stream}[{p_idx}:v]overlay=0:0:enable='between(t,{p_st:.2f},{p_et:.2f})':eof_action=pass[{v_out_label}]"
        )
        base_v_stream = f"[{v_out_label}]"

    # Contextual Quote Callout Overlay
    if quote_idx is not None:
        v_filters.append(
            f"[{quote_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,"
            f"fade=t=in:st={quote_start:.2f}:d=0.25:alpha=1,"
            f"fade=t=out:st={quote_end - 0.25:.2f}:d=0.25:alpha=1[v_quote]"
        )
        v_filters.append(
            f"{base_v_stream}[v_quote]overlay=0:0:enable='between(t,{quote_start:.2f},{quote_end:.2f})':eof_action=pass[v_with_quote]"
        )
        base_v_stream = "[v_with_quote]"

    # Contextual Analysis Red Flags Card Overlay
    if analysis_card_idx is not None:
        v_filters.append(
            f"[{analysis_card_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,"
            f"fade=t=in:st={ac_start:.2f}:d=0.25:alpha=1,"
            f"fade=t=out:st={ac_end - 0.25:.2f}:d=0.25:alpha=1[v_ac]"
        )
        v_filters.append(
            f"{base_v_stream}[v_ac]overlay=0:0:enable='between(t,{ac_start:.2f},{ac_end:.2f})':eof_action=pass[v_with_ac]"
        )
        base_v_stream = "[v_with_ac]"

    # Contextual Community Verdict Card Overlay (Slot 3)
    if verdict_idx is not None:
        v_filters.append(
            f"[{verdict_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,"
            f"fade=t=in:st={v_start:.2f}:d=0.25:alpha=1,"
            f"fade=t=out:st={v_end - 0.25:.2f}:d=0.25:alpha=1[v_verdict]"
        )
        v_filters.append(
            f"{base_v_stream}[v_verdict]overlay=0:0:enable='between(t,{v_start:.2f},{v_end:.2f})':eof_action=pass[v_with_verdict]"
        )
        base_v_stream = "[v_with_verdict]"

    # Graphical Breakdown Badge Overlay with smooth fade-in and fade-out
    if badge_idx is not None:
        b_fade_d = 0.25
        b_fade_in = analysis_start_time
        b_fade_out = max(analysis_start_time + 0.5, analysis_end_time - b_fade_d)
        v_filters.append(
            f"[{badge_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,"
            f"fade=t=in:st={b_fade_in:.2f}:d={b_fade_d:.2f}:alpha=1,"
            f"fade=t=out:st={b_fade_out:.2f}:d={b_fade_d:.2f}:alpha=1[badge]"
        )
        v_filters.append(
            f"{base_v_stream}[badge]overlay=0:0:enable='between(t,{analysis_start_time:.2f},{analysis_end_time:.2f})':eof_action=pass[v_analyzed]"
        )
        base_v_stream = "[v_analyzed]"

    # Subtitles layer on top of all visual elements
    v_filters.append(f"{base_v_stream}subtitles='{subtitle_path_ffmpeg}'[v_out]")

    # ----------------------------------------------------
    # Audio Filter Graph: Dynamic Ducking (Rock-Solid Constant Volume Matching Short 2 & 3)
    # ----------------------------------------------------
    voice_vol = float(os.getenv("VOICE_BASE_VOLUME", "0.22"))
    a_filters = []
    if music_idx is not None:
        music_base_vol = float(os.getenv("MUSIC_BASE_VOLUME", "0.030"))
        a_filters.append(
            f"[{voice_idx}:a]volume={voice_vol:.3f},asplit=2[v_main][v_sc];"
            f"[{music_idx}:a]atrim=0:{audio_duration:.2f},asetpts=PTS-STARTPTS,volume={music_base_vol:.3f}[m_vol];"
            f"[m_vol][v_sc]sidechaincompress=threshold=0.008:ratio=8:attack=150:release=650:makeup=1[m_ducked];"
            f"[v_main][m_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
        )
    else:
        a_filters.append(
            f"[{voice_idx}:a]volume={voice_vol:.3f},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a_out]"
        )

    full_filter_complex = ";".join(v_filters) + ";" + ";".join(a_filters)
    map_args = ["-filter_complex", full_filter_complex, "-map", "[v_out]", "-map", "[a_out]"]

    threads_count = os.getenv("FFMPEG_THREADS", "0")

    temp_output_path = output_path + ".tmp.mp4"
    if os.path.exists(temp_output_path):
        try:
            os.remove(temp_output_path)
        except Exception:
            pass

    cmd = [
        "ffmpeg",
        "-y",
    ] + input_args + [
        "-c:v", encoder,
        "-preset", "ultrafast",
        "-crf", "24",
        "-threads", threads_count,
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"
    ] + map_args + [
        "-t", f"{audio_duration:.2f}",
        temp_output_path
    ]

    print(f"[DEBUG] Running FFmpeg command:\n{' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"[DEBUG] FFmpeg STDOUT:\n{result.stdout}")
        print(f"[DEBUG] FFmpeg STDERR:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        if os.path.exists(temp_output_path):
            try:
                os.remove(temp_output_path)
            except Exception:
                pass
        error_msg = f"[ERROR] FFmpeg failed with exit code {e.returncode}:\n{e.stderr}"
        print(error_msg)
        raise RuntimeError(error_msg)

    if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) < 100 * 1024:
        raise FileNotFoundError(f"[ERROR] Output video not created or too small at: {temp_output_path}")

    # Atomic rename to final output path
    os.replace(temp_output_path, output_path)

    # Ensure thumbnail exists for YouTube upload (preserve pristine PIL card composite)
    extracted_thumb_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/thumb_{story_name}.png"))
    if not os.path.exists(extracted_thumb_path):
        try:
            # Fallback extraction from video intro during title display
            extract_time = f"{max(0.2, min(1.0, title_end_time * 0.4)):.2f}"
            extract_cmd = [
                "ffmpeg", "-y",
                "-i", output_path,
                "-ss", extract_time,
                "-frames:v", "1",
                "-update", "1",
                extracted_thumb_path
            ]
            subprocess.run(extract_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            print(f"[SUCCESS] Extracted video frame thumbnail: {extracted_thumb_path}")
        except Exception as e:
            print(f"⚠️ Thumbnail extraction warning: {e}")
    else:
        print(f"[SUCCESS] Verified composite thumbnail: {extracted_thumb_path}")

    print(f"[SUCCESS] Video rendered successfully at: {output_path}")
    return output_path

if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d")
    story_idx = sys.argv[2] if len(sys.argv) > 2 else "1"
    render_video(target_date, story_name=story_idx)

