import os
import random
import subprocess
import wave
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GAMEPLAY_DIR = os.path.join(PROJECT_ROOT, "assets", "gameplays")

_video_duration_cache = {}

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
    Prepares gameplay video input using either:
    - Method A (offset): Random start timestamp from a long video (Default)
    - Method B (montage): Rapid 5-10s dynamic cuts stitched across clips
    """
    all_clips = get_available_gameplay_clips()

    if not all_clips and (not specific_clip_path or not os.path.exists(specific_clip_path)):
        raise FileNotFoundError(f"[ERROR] No gameplay video clips found in {GAMEPLAY_DIR}")

    # Boolean toggle: ENABLE_MONTAGE=false (Method A: Offset) or true (Method B: Montage)
    enable_montage = os.getenv("ENABLE_MONTAGE", "false").strip().lower() in ("true", "1", "yes")
    if not enable_montage and os.getenv("GAMEPLAY_MODE", "").strip().lower() == "montage":
        enable_montage = True

    target_duration = audio_duration + 5.0  # 5 second buffer for safety

    # Determine candidate clip for Method A
    candidate_clip = None
    if specific_clip_path and os.path.exists(specific_clip_path):
        candidate_clip = specific_clip_path
    elif all_clips:
        candidate_clip = random.choice(all_clips)

    # ----------------------------------------------------
    # METHOD A: Random Start Offset (Default when ENABLE_MONTAGE=false)
    # ----------------------------------------------------
    if not enable_montage and candidate_clip:
        clip_dur = get_video_duration(candidate_clip)
        if clip_dur >= target_duration:
            max_start = max(0.0, clip_dur - target_duration)
            start_offset = random.uniform(0.0, max_start)
            print(f"[DEBUG] [Method A - Offset] Chosen clip: {os.path.basename(candidate_clip)} (Length: {clip_dur:.1f}s) starting at random offset: {start_offset:.1f}s")
            return ["-ss", f"{start_offset:.2f}", "-i", candidate_clip.replace("\\", "/")], None

    # ----------------------------------------------------
    # METHOD B: Dynamic Random Montage (or Fallback if clip too short)
    # ----------------------------------------------------
    print(f"[DEBUG] [Method B - Montage] Slicing random 5-10s scenes across clips...")
    selected_slices = []
    accumulated_duration = 0.0
    pool = list(all_clips)
    random.shuffle(pool)

    while accumulated_duration < target_duration and pool:
        clip = pool.pop(0)
        dur = get_video_duration(clip)

        slice_len = min(dur, random.uniform(5.0, 10.0))
        max_start = max(0.0, dur - slice_len)
        start_pt = random.uniform(0.0, max_start)
        end_pt = start_pt + slice_len

        selected_slices.append((clip, start_pt, end_pt))
        accumulated_duration += slice_len

        if not pool:
            pool = list(all_clips)
            random.shuffle(pool)

    print(f"[DEBUG] Stitched {len(selected_slices)} random scenes for total ~{accumulated_duration:.1f}s")

    # Create temporary concat list for FFmpeg using inpoint & outpoint
    temp_concat = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    for clip_path, in_pt, out_pt in selected_slices:
        formatted_path = clip_path.replace("\\", "/")
        temp_concat.write(f"file '{formatted_path}'\n")
        temp_concat.write(f"inpoint {in_pt:.2f}\n")
        temp_concat.write(f"outpoint {out_pt:.2f}\n")
    temp_concat.close()

    input_args = ["-f", "concat", "-safe", "0", "-i", temp_concat.name.replace("\\", "/")]
    return input_args, temp_concat.name


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

    # Prepare gameplay video input (Method A or Method B)
    gameplay_input_args, temp_concat_file = prepare_gameplay_input(audio_duration, specific_clip_path=gameplay_path)

    # Check if thumbnail image exists for intro display
    thumb_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"reddit_stories/{date_str}/thumb_{story_name}.png"))
    has_thumb = os.path.exists(thumb_path)

    # Read title duration from timing JSON
    timing_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"audio/{date_str}/voice_{story_name}_timing.json"))
    title_end_time = 3.0
    if os.path.exists(timing_path):
        try:
            with open(timing_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                if isinstance(tdata, dict):
                    title_end_time = float(tdata.get("title_end_time", 3.0))
        except Exception:
            pass

    def ffmpeg_path(path):
        return path.replace("\\", "/").replace(":", "\\:")

    audio_path_ffmpeg = audio_path.replace("\\", "/")
    subtitle_path_ffmpeg = ffmpeg_path(subtitle_path)

    w, h = (1080, 1920) if format == "short" else (1920, 1080)

    encoder = get_best_video_encoder()
    print(f"[DEBUG] Using video encoder: {encoder}")

    extra_inputs = []
    if has_thumb:
        thumb_path_ffmpeg = thumb_path.replace("\\", "/")
        extra_inputs = ["-i", thumb_path_ffmpeg]
        fade_d = 0.4
        fade_st = max(0.1, title_end_time - fade_d)
        
        filter_complex = (
            f"[2:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuva420p,fade=t=out:st={fade_st:.2f}:d={fade_d:.2f}:alpha=1[thumb];"
            f"[0:v]fps=30,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1[gameplay];"
            f"[gameplay][thumb]overlay=0:0:enable='between(t,0,{title_end_time:.2f})'[v_merged];"
            f"[v_merged]subtitles='{subtitle_path_ffmpeg}'[v_out]"
        )
        map_args = ["-filter_complex", filter_complex, "-map", "[v_out]", "-map", "1:a:0"]
    else:
        vf_filter = (
            f"fps=30,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"setsar=1,"
            f"subtitles='{subtitle_path_ffmpeg}'"
        )
        map_args = ["-vf", vf_filter, "-map", "0:v:0", "-map", "1:a:0"]

    cmd = [
        "ffmpeg",
        "-y"
    ] + gameplay_input_args + [
        "-i", audio_path_ffmpeg
    ] + extra_inputs + [
        "-c:v", encoder,
        "-preset", "ultrafast",
        "-crf", "24",
        "-threads", "0",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"
    ] + map_args + [
        "-shortest",
        "-map_metadata", "-1",       # Strip all source metadata
        "-metadata", "title=",        # Remove container title
        "-metadata:s:v:0", "title=",  # Remove video stream title
        "-metadata:s:a:0", "title=",  # Remove audio stream title
        output_path
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
        error_msg = f"[ERROR] FFmpeg failed with exit code {e.returncode}:\n{e.stderr}"
        print(error_msg)
        raise RuntimeError(error_msg)
    finally:
        # Clean up temporary concat file if created
        if temp_concat_file and os.path.exists(temp_concat_file):
            try:
                os.remove(temp_concat_file)
            except Exception:
                pass

    if not os.path.exists(output_path):
        raise FileNotFoundError(f"[ERROR] Output video not created at: {output_path}")

    print(f"[SUCCESS] Video rendered successfully at: {output_path}")
    return output_path
