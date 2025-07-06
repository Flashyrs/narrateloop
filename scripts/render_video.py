import os
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def render_video(date_str, gameplay_path, story_name, format="short"):
    print(f"[DEBUG] Starting render_video for story: {story_name} on date: {date_str}, format: {format}")

    audio_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"audio/{date_str}/voice_{story_name}.wav"))
    subtitle_path = os.path.abspath(os.path.join(PROJECT_ROOT, f"subtitles/{date_str}_{story_name}_{format}.ass"))
    output_dir = os.path.join(PROJECT_ROOT, f"output/{date_str}")
    output_path = os.path.abspath(os.path.join(output_dir, f"final_{story_name}.mp4"))

    print(f"[DEBUG] Paths:")
    print(f"  Audio path: {audio_path}")
    print(f"  Subtitle path: {subtitle_path}")
    print(f"  Gameplay path: {gameplay_path}")
    print(f"  Output path: {output_path}")

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"[ERROR] Audio file not found: {audio_path}")
    if not os.path.exists(subtitle_path):
        raise FileNotFoundError(f"[ERROR] Subtitle file not found: {subtitle_path}")
    if not os.path.exists(gameplay_path):
        raise FileNotFoundError(f"[ERROR] Gameplay video not found: {gameplay_path}")

    def ffmpeg_path(path):
        return path.replace("\\", "/").replace(":", "\\:")

    gameplay_path_ffmpeg = gameplay_path.replace("\\", "/")
    audio_path_ffmpeg = audio_path.replace("\\", "/")
    subtitle_path_ffmpeg = ffmpeg_path(subtitle_path)

    if format == "short":
        vf_filter = (
            f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
            f"scale=1080:1920,"
            f"subtitles='{subtitle_path_ffmpeg}'"
        )
    else:  # "video" format
        vf_filter = f"subtitles='{subtitle_path_ffmpeg}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", gameplay_path_ffmpeg,
        "-i", audio_path_ffmpeg,
        "-c:v", "h264_nvenc",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf_filter,
        "-shortest",
        "-crf", "23",
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

    if not os.path.exists(output_path):
        raise FileNotFoundError(f"[ERROR] Output video not created at: {output_path}")

    print(f"[SUCCESS] Video rendered successfully at: {output_path}")
    return output_path
