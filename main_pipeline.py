import os
import sys
import json
import re
import time
import subprocess
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from scripts.telegram_notify import send_telegram_log, should_stop, get_task_flags
from scripts.fetch_reddit import fetch_reddit_posts
from scripts.generate_tts import generate_tts
from scripts.generate_subs import generate_subs
from scripts.render_video import render_video
from scripts.upload_to_youtube import upload_video, generate_title_and_description
from scripts.refresh_pending_queue import refresh_pending_queue

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
QUEUE_PATH = os.path.join(PROJECT_ROOT, "queue", "pending.txt")
REDDIT_DIR = os.path.join(PROJECT_ROOT, "reddit_stories")
GAMEPLAY_DIR = os.path.join(PROJECT_ROOT, "assets", "gameplays")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

active_flags = {
    "tts": True,
    "subs": True,
    "render": True,
    "upload": True
}


def get_current_time():
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()


def log(message, date_str=None, telegram=False, tts_progress=False):
    timestamp = get_current_time().strftime("[%H:%M:%S]")
    full_message = f"{timestamp} {message}"
    print(full_message)

    if date_str:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, f"{date_str}.log"), "a", encoding="utf-8") as f:
            f.write(full_message + "\n")

    if telegram:
        keywords = ["error", "uploaded", "uploading", "generating", "final video not found",
                    "processing stopped", "already uploaded", "cleanup", "deleted"]
        lower_msg = message.lower()
        if any(k in lower_msg for k in keywords) or tts_progress:
            send_telegram_log(full_message if tts_progress else f"⚠️ {full_message}")

def get_story_files(folder_path):
    files = [f for f in os.listdir(folder_path) if f.startswith("story_") and f.endswith(".json")]
    files.sort(key=lambda name: int(re.search(r"story_(\d+)", name).group(1)))
    return files

def cleanup_old_data(retain_days=2):
    deleted_dates = set()

    def cleanup_dir(base_path, label):
        if not os.path.exists(base_path): return
        folders = [d for d in os.listdir(base_path) if re.match(r"\d{8}", d)]
        folders = [d for d in folders if os.path.isdir(os.path.join(base_path, d))]

        today = datetime.now().strftime("%Y%m%d")
        folders = [d for d in folders if d <= today]
        folders = sorted(folders, reverse=True)
        for d in folders[retain_days:]:
            try:
                import shutil
                shutil.rmtree(os.path.join(base_path, d))
                deleted_dates.add(d)
                log(f"[Cleanup] Deleted {label} data for {d}", telegram=True)
            except Exception as e:
                log(f"[Cleanup] Failed to delete {label} data for {d}: {e}", telegram=True)

    cleanup_dir(os.path.join(PROJECT_ROOT, "audio"), "audio")
    cleanup_dir(os.path.join(PROJECT_ROOT, "output"), "output")
    cleanup_dir(os.path.join(PROJECT_ROOT, "reddit_stories"), "reddit_stories")

    subs_dir = os.path.join(PROJECT_ROOT, "subtitles")
    if os.path.exists(subs_dir):
        files = os.listdir(subs_dir)
        dates = sorted(set(f[:8] for f in files if re.match(r"\d{8}_\d+_(short|video)\.ass", f)), reverse=True)
        keep = set(dates[:retain_days])
        for f in files:
            if f[:8] not in keep:
                try:
                    os.remove(os.path.join(subs_dir, f))
                    deleted_dates.add(f[:8])
                    log(f"[Cleanup] Deleted subtitle: {f}", telegram=True)
                except Exception as e:
                    log(f"[Cleanup] Failed to delete subtitle {f}: {e}", telegram=True)

    if deleted_dates:
        log(f"[Cleanup] Removed data for: {', '.join(deleted_dates)}", telegram=True)
    else:
        log("[Cleanup] No old data to remove.", telegram=True)

def get_next_valid_gameplay():
    refresh_pending_queue()
    if not os.path.exists(QUEUE_PATH): raise Exception("Gameplay queue file missing.")
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    for i, clip in enumerate(lines):
        path = os.path.join(GAMEPLAY_DIR, f"{clip}.mp4")
        if os.path.exists(path):
            with open(QUEUE_PATH, "w", encoding="utf-8") as f:
                f.writelines(l + "\n" for j, l in enumerate(lines) if j != i)
            return clip, path
    raise Exception("No valid gameplay clip found in queue.")

def run_pipeline(upload=False):
    start_time = time.time()
    date_str = get_current_time().strftime("%Y%m%d")
    cleanup_old_data()
    refresh_pending_queue()

    reddit_path = os.path.join(REDDIT_DIR, date_str)
    if not os.path.exists(reddit_path) or len(os.listdir(reddit_path)) < 3:
        log("Fetching Reddit stories...", date_str, telegram=True)
        fetch_reddit_posts()

    story_files = get_story_files(reddit_path)
    upload_done = False
    task_flags = get_task_flags()

    for filename in story_files:
        if should_stop:
            log(" Processing stopped by user command.", date_str, telegram=True)
            return

        story_index = int(re.search(r"story_(\d+)", filename).group(1))
        with open(os.path.join(reddit_path, filename), encoding="utf-8") as f:
            story = json.load(f)

        fmt = story.get("format", "short")
        audio_dir = os.path.join(PROJECT_ROOT, "audio", date_str)
        output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
        audio_path = os.path.join(audio_dir, f"voice_{story_index}.wav")
        subs_path = os.path.join(PROJECT_ROOT, "subtitles", f"{date_str}_{story_index}_{fmt}.ass")
        output_path = os.path.join(output_dir, f"final_{story_index}.mp4")
        uploaded_log = os.path.join(output_dir, "uploaded.txt")

        os.makedirs(audio_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(audio_path) and task_flags.get("tts", True):
            log(f"[{filename}] Generating TTS...", date_str, telegram=True)
            generate_tts(date_str, story_index)

        if not os.path.exists(subs_path) and task_flags.get("subs", True):
            log(f"[{filename}] Generating subs ({fmt})...", date_str, telegram=True)
            generate_subs(date_str, story_index, format=fmt)

        if not os.path.exists(output_path) and task_flags.get("render", True):
            try:
                clip, clip_path = get_next_valid_gameplay()
                log(f"[{filename}] Rendering with gameplay: {clip}", date_str, telegram=True)
                render_video(date_str, clip_path, story_index, format=fmt)
            except Exception as e:
                log(f"[{filename}] Error: {e}", date_str, telegram=True)
                continue

        if upload and not upload_done and task_flags.get("upload", True):
            already_uploaded = False
            if os.path.exists(uploaded_log):
                with open(uploaded_log, "r") as f:
                    already_uploaded = any(f"final_{story_index}.mp4" in line for line in f)

            if not already_uploaded:
                title, description, tags = generate_title_and_description(story)
                thumbnail_path_png = os.path.join(reddit_path, f"thumb_{story_index}.png")
                thumbnail_path_jpg = os.path.join(reddit_path, f"thumb_{story_index}.jpg")
                thumbnail_path = thumbnail_path_png if os.path.exists(thumbnail_path_png) else (
                    thumbnail_path_jpg if os.path.exists(thumbnail_path_jpg) else None
                )
                url = upload_video(output_path, title, description, tags, thumbnail_path=thumbnail_path)

                with open(uploaded_log, "a", encoding="utf-8") as f:
                    f.write(f"final_{story_index}.mp4 | {title} | {url}\n")
                log(f"[{filename}] Uploaded: {url}", date_str, telegram=True)
                upload_done = True
                break
            elif already_uploaded:
                log(f"[{filename}] Already uploaded.", date_str)

    if upload and not upload_done:
        log("No pending videos to upload.", date_str, telegram=True)

    elapsed = round(time.time() - start_time, 2)
    send_telegram_log(f"⏳ Startup time: {elapsed} sec")

def run_pipeline_upload_specific(index):
    date_str = get_current_time().strftime("%Y%m%d")
    output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
    uploaded_log = os.path.join(output_dir, "uploaded.txt")
    reddit_day_path = os.path.join(REDDIT_DIR, date_str)
    filename = f"story_{index}.json"
    story_path = os.path.join(reddit_day_path, filename)

    if not os.path.exists(story_path):
        log(f"Story file for index {index} not found.", date_str, telegram=True)
        return

    with open(story_path, "r", encoding="utf-8") as f:
        story = json.load(f)

    format = story.get("format", "short")
    output_path = os.path.join(output_dir, f"final_{index}.mp4")

    # If requested index is already uploaded or file missing, find next pending video today
    already_uploaded = []
    if os.path.exists(uploaded_log):
        with open(uploaded_log, "r", encoding="utf-8") as f:
            already_uploaded = f.read().splitlines()

    if not os.path.exists(output_path) or any(f"final_{index}.mp4" in line for line in already_uploaded):
        found_next = False
        for cand in [1, 2, 3]:
            cand_video = f"final_{cand}.mp4"
            cand_path = os.path.join(output_dir, cand_video)
            cand_story = os.path.join(reddit_day_path, f"story_{cand}.json")
            if os.path.exists(cand_path) and os.path.exists(cand_story) and not any(cand_video in line for line in already_uploaded):
                log(f"Selecting next pending video for upload: final_{cand}.mp4 (slot {index})", date_str, telegram=True)
                index = cand
                filename = f"story_{index}.json"
                story_path = cand_story
                output_path = cand_path
                with open(story_path, "r", encoding="utf-8") as sf:
                    story = json.load(sf)
                found_next = True
                break

        if not found_next:
            existing_videos = [f"final_{c}.mp4" for c in [1, 2, 3] if os.path.exists(os.path.join(output_dir, f"final_{c}.mp4"))]
            if not existing_videos:
                log(f"⚠️ No rendered videos found in {output_dir} for {date_str} to upload.", date_str, telegram=True)
            else:
                log(f"All available videos for {date_str} have already been uploaded.", date_str, telegram=True)
            return

    # Integrity verification: check that video has valid streams and non-zero duration
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        dur = float(probe.stdout.strip())
        if dur < 3.0:
            log(f"❌ Aborting upload: final_{index}.mp4 is invalid or corrupted ({dur}s).", date_str, telegram=True)
            return
    except Exception as pe:
        log(f"❌ Aborting upload: final_{index}.mp4 verification error: {pe}", date_str, telegram=True)
        return

    # ✅ Now safe to generate title, etc.
    title, description, tags = generate_title_and_description(story)
    thumbnail_path_png = os.path.join(reddit_day_path, f"thumb_{index}.png")
    thumbnail_path_jpg = os.path.join(reddit_day_path, f"thumb_{index}.jpg")
    thumbnail_path = thumbnail_path_png if os.path.exists(thumbnail_path_png) else (
        thumbnail_path_jpg if os.path.exists(thumbnail_path_jpg) else None
    )

    video_url = upload_video(output_path, title, description, tags, thumbnail_path=thumbnail_path)

    # ✅ Log and write upload data
    with open(uploaded_log, "a", encoding="utf-8") as f:
        f.write(f"final_{index}.mp4 | {title} | {video_url}\n")

    log(f"[story_{index}.json] Uploaded: {video_url}", date_str, telegram=True)


def get_upload_status(date_str=None):
    if not date_str:
        date_str = get_current_time().strftime("%Y%m%d")

    output_base = os.path.join(PROJECT_ROOT, "output", date_str)
    if not os.path.exists(output_base):
        return f"No output found for date: {date_str}"

    status_report = []

    d = date_str
    full_path = output_base
    if not os.path.isdir(full_path):
        return f"No folder for output/{d}"

    uploaded_log_path = os.path.join(full_path, "uploaded.txt")
    uploaded_info = {}
    if os.path.exists(uploaded_log_path):
        with open(uploaded_log_path, "r") as f:
            for line in f:
                parts = line.strip().split(" | ")
                if len(parts) == 3:
                    uploaded_info[parts[0]] = {"title": parts[1], "url": parts[2]}
                else:
                    uploaded_info[parts[0]] = {"title": parts[0], "url": ""}

    all_videos = sorted([f for f in os.listdir(full_path) if f.startswith("final_") and f.endswith(".mp4")])
    reddit_path = os.path.join(REDDIT_DIR, d)
    format_lookup = {}

    if os.path.exists(reddit_path):
        for f in os.listdir(reddit_path):
            if f.startswith("story_") and f.endswith(".json"):
                with open(os.path.join(reddit_path, f), encoding="utf-8") as jf:
                    data = json.load(jf)
                    idx = re.search(r"story_(\d+)", f).group(1)
                    format_lookup[f"final_{idx}.mp4"] = {
                        "title": data.get("title", f"story_{idx}"),
                        "format": data.get("format", "?")
                    }

    uploaded = []
    pending = []
    for vid in all_videos:
        info = format_lookup.get(vid, {"title": vid, "format": "?"})
        if vid in uploaded_info:
            link = uploaded_info[vid].get("url", "")
            title = uploaded_info[vid].get("title", info["title"])
            uploaded.append(f"[{info['format']}] [{title}](<{link}>)" if link else f"{title} [{info['format']}] ✅")
        else:
            pending.append(f"{info['title']} [{info['format']}]")

    status = f"\n📅 {d}:\n"
    status += f" 🎬 Uploaded:\n   • " + ("\n   • ".join(uploaded) if uploaded else "None") + "\n"
    status += f" 🕒 Pending:\n   • " + ("\n   • ".join(pending) if pending else "None") + "\n"
    status_report.append(status)

    return "\n".join(status_report)


if __name__ == "__main__":
    upload_flag = "--upload" in sys.argv
    run_pipeline(upload=upload_flag)




# import os
# import json
# import torch
# import re
# from datetime import datetime
# from scripts.telegram_notify import send_telegram_log, should_stop
# from scripts.fetch_reddit import fetch_reddit_posts
# from scripts.generate_tts import generate_tts
# from scripts.generate_subs import generate_subs
# from scripts.render_video import render_video
# from scripts.upload_to_youtube import upload_video, generate_title_and_description
# from scripts.refresh_pending_queue import refresh_pending_queue

# PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
# QUEUE_PATH = os.path.join(PROJECT_ROOT, "queue", "pending.txt")
# REDDIT_DIR = os.path.join(PROJECT_ROOT, "reddit_stories")
# GAMEPLAY_DIR = os.path.join(PROJECT_ROOT, "assets", "gameplays")
# LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# def log(message, date_str=None, telegram=False, tts_progress=False):
#     timestamp = datetime.now().strftime("[%H:%M:%S]")
#     full_message = f"{timestamp} {message}"
#     print(full_message)

#     if date_str:
#         os.makedirs(LOG_DIR, exist_ok=True)
#         with open(os.path.join(LOG_DIR, f"{date_str}.log"), "a", encoding="utf-8") as f:
#             f.write(full_message + "\n")

#     if telegram:
#         keywords = ["error", "uploaded", "uploading", "generating", "final video not found",
#                     "processing stopped", "already uploaded", "cleanup", "deleted"]
#         lower_msg = message.lower()
#         if any(k in lower_msg for k in keywords) or tts_progress:
#             send_telegram_log(full_message if tts_progress else f"⚠️ {full_message}")

# def get_story_files(folder_path):
#     files = [f for f in os.listdir(folder_path) if f.startswith("story_") and f.endswith(".json")]
#     files.sort(key=lambda name: int(re.search(r"story_(\d+)", name).group(1)))
#     return files

# def cleanup_old_data(retain_days=2):
#     deleted_dates = set()

#     def cleanup_dir(base_path, label):
#         if not os.path.exists(base_path): return
#         folders = [d for d in os.listdir(base_path) if re.match(r"\d{8}", d)]
#         folders = [d for d in folders if os.path.isdir(os.path.join(base_path, d))]

#         # Keep only dates ≤ today
#         today = datetime.now().strftime("%Y%m%d")
#         folders = [d for d in folders if d <= today]

#         folders = sorted(folders, reverse=True)
#         for d in folders[retain_days:]:
#             try:
#                 import shutil
#                 shutil.rmtree(os.path.join(base_path, d))
#                 deleted_dates.add(d)
#                 log(f"[Cleanup] Deleted {label} data for {d}", telegram=True)
#             except Exception as e:
#                 log(f"[Cleanup] Failed to delete {label} data for {d}: {e}", telegram=True)


#     cleanup_dir(os.path.join(PROJECT_ROOT, "audio"), "audio")
#     cleanup_dir(os.path.join(PROJECT_ROOT, "output"), "output")
#     cleanup_dir(os.path.join(PROJECT_ROOT, "reddit_stories"), "reddit_stories")

#     subs_dir = os.path.join(PROJECT_ROOT, "subtitles")
#     if os.path.exists(subs_dir):
#         files = os.listdir(subs_dir)
#         dates = sorted(set(f[:8] for f in files if re.match(r"\d{8}_\d+_(short|video)\.ass", f)), reverse=True)
#         keep = set(dates[:retain_days])
#         for f in files:
#             if f[:8] not in keep:
#                 try:
#                     os.remove(os.path.join(subs_dir, f))
#                     deleted_dates.add(f[:8])
#                     log(f"[Cleanup] Deleted subtitle: {f}", telegram=True)
#                 except Exception as e:
#                     log(f"[Cleanup] Failed to delete subtitle {f}: {e}", telegram=True)

#     if deleted_dates:
#         log(f"[Cleanup] Removed data for: {', '.join(deleted_dates)}", telegram=True)
#     else:
#         log("[Cleanup] No old data to remove.", telegram=True)

# def get_next_valid_gameplay():
#     refresh_pending_queue()
#     if not os.path.exists(QUEUE_PATH): raise Exception("Gameplay queue file missing.")
#     with open(QUEUE_PATH, "r", encoding="utf-8") as f:
#         lines = [line.strip() for line in f if line.strip()]
#     for i, clip in enumerate(lines):
#         path = os.path.join(GAMEPLAY_DIR, f"{clip}.mp4")
#         if os.path.exists(path):
#             with open(QUEUE_PATH, "w", encoding="utf-8") as f:
#                 f.writelines(l + "\n" for j, l in enumerate(lines) if j != i)
#             return clip, path
#     raise Exception("No valid gameplay clip found in queue.")

# def run_pipeline(upload=False):
#     date_str = datetime.now().strftime("%Y%m%d")
#     cleanup_old_data()
#     refresh_pending_queue()

#     reddit_path = os.path.join(REDDIT_DIR, date_str)
#     if not os.path.exists(reddit_path) or len(os.listdir(reddit_path)) < 3:
#         log("Fetching Reddit stories...", date_str, telegram=True)
#         fetch_reddit_posts()

#     story_files = get_story_files(reddit_path)
#     upload_done = False

#     for filename in story_files:
#         if should_stop:
#             log(" Processing stopped by user command.", date_str, telegram=True)
#             return

#         story_index = int(re.search(r"story_(\d+)", filename).group(1))
#         with open(os.path.join(reddit_path, filename), encoding="utf-8") as f:
#             story = json.load(f)

#         fmt = story.get("format", "short")
#         audio_dir = os.path.join(PROJECT_ROOT, "audio", date_str)
#         output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
#         audio_path = os.path.join(audio_dir, f"voice_{story_index}.wav")
#         subs_path = os.path.join(PROJECT_ROOT, "subtitles", f"{date_str}_{story_index}_{fmt}.ass")
#         output_path = os.path.join(output_dir, f"final_{story_index}.mp4")
#         uploaded_log = os.path.join(output_dir, "uploaded.txt")

#         os.makedirs(audio_dir, exist_ok=True)
#         os.makedirs(output_dir, exist_ok=True)

#         if not os.path.exists(audio_path):
#             log(f"[{filename}] Generating TTS...", date_str, telegram=True)
#             generate_tts(date_str, story_index)

#         if not os.path.exists(subs_path):
#             log(f"[{filename}] Generating subs ({fmt})...", date_str, telegram=True)
#             generate_subs(date_str, story_index, format=fmt)

#         if not os.path.exists(output_path):
#             try:
#                 clip, clip_path = get_next_valid_gameplay()
#                 log(f"[{filename}] Rendering with gameplay: {clip}", date_str, telegram=True)
#                 render_video(date_str, clip_path, story_index, format=fmt)
#             except Exception as e:
#                 log(f"[{filename}] Error: {e}", date_str, telegram=True)
#                 continue

#         if upload:
#             already_uploaded = False
#             if os.path.exists(uploaded_log):
#                 with open(uploaded_log, "r") as f:
#                     already_uploaded = any(f"final_{story_index}.mp4" in line for line in f)

#             if not already_uploaded and not upload_done:
#                 title, description, tags = generate_title_and_description(story)
#                 thumbnail_path_png = os.path.join(reddit_path, f"thumb_{story_index}.png")
#                 thumbnail_path_jpg = os.path.join(reddit_path, f"thumb_{story_index}.jpg")
#                 thumbnail_path = thumbnail_path_png if os.path.exists(thumbnail_path_png) else (
#                     thumbnail_path_jpg if os.path.exists(thumbnail_path_jpg) else None
#                 )
#                 url = upload_video(output_path, title, description, tags, thumbnail_path=thumbnail_path)


#                 with open(uploaded_log, "a", encoding="utf-8") as f:
#                     f.write(f"final_{story_index}.mp4 | {title} | {url}\n")
#                 log(f"[{filename}] Uploaded: {url}", date_str, telegram=True)
#                 upload_done = True
#                 break
#             elif already_uploaded:
#                 log(f"[{filename}] Already uploaded.", date_str)

#     if upload and not upload_done:
#         log("No pending videos to upload.", date_str, telegram=True)

# def run_pipeline_upload_specific(index):
#     date_str = datetime.now().strftime("%Y%m%d")
#     output_dir = os.path.join(PROJECT_ROOT, "output", date_str)
#     uploaded_log = os.path.join(output_dir, "uploaded.txt")
#     reddit_day_path = os.path.join(REDDIT_DIR, date_str)
#     filename = f"story_{index}.json"
#     story_path = os.path.join(reddit_day_path, filename)

#     if not os.path.exists(story_path):
#         log(f"Story file for index {index} not found.", date_str, telegram=True)
#         return

#     with open(story_path, "r", encoding="utf-8") as f:
#         story = json.load(f)

#     format = story.get("format", "short")
#     output_path = os.path.join(output_dir, f"final_{index}.mp4")
#     if not os.path.exists(output_path):
#         log(f"Final video final_{index}.mp4 not found.", date_str, telegram=True)
#         return

#     # Check if already uploaded
#     if os.path.exists(uploaded_log):
#         with open(uploaded_log, "r") as f:
#             if any(f"final_{index}.mp4" in line for line in f):
#                 log(f"Video final_{index}.mp4 already uploaded.", date_str, telegram=True)
#                 return

#     # ✅ Now safe to generate title, etc.
#     title, description, tags = generate_title_and_description(story)
#     thumbnail_path_png = os.path.join(reddit_day_path, f"thumb_{index}.png")
#     thumbnail_path_jpg = os.path.join(reddit_day_path, f"thumb_{index}.jpg")
#     thumbnail_path = thumbnail_path_png if os.path.exists(thumbnail_path_png) else (
#         thumbnail_path_jpg if os.path.exists(thumbnail_path_jpg) else None
#     )

#     video_url = upload_video(output_path, title, description, tags, thumbnail_path=thumbnail_path)

#     # ✅ Log and write upload data
#     with open(uploaded_log, "a", encoding="utf-8") as f:
#         f.write(f"final_{index}.mp4 | {title} | {video_url}\n")

#     log(f"[story_{index}.json] Uploaded: {video_url}", date_str, telegram=True)


# def get_upload_status(date_str=None):
#     if not date_str:
#         date_str = datetime.now().strftime("%Y%m%d")

#     output_base = os.path.join(PROJECT_ROOT, "output", date_str)
#     if not os.path.exists(output_base):
#         return f"No output found for date: {date_str}"

#     status_report = []

#     d = date_str
#     full_path = output_base
#     if not os.path.isdir(full_path):
#         return f"No folder for output/{d}"

#     uploaded_log_path = os.path.join(full_path, "uploaded.txt")
#     uploaded_info = {}
#     if os.path.exists(uploaded_log_path):
#         with open(uploaded_log_path, "r") as f:
#             for line in f:
#                 parts = line.strip().split(" | ")
#                 if len(parts) == 3:
#                     uploaded_info[parts[0]] = {"title": parts[1], "url": parts[2]}
#                 else:
#                     uploaded_info[parts[0]] = {"title": parts[0], "url": ""}

#     all_videos = sorted([f for f in os.listdir(full_path) if f.startswith("final_") and f.endswith(".mp4")])
#     reddit_path = os.path.join(REDDIT_DIR, d)
#     format_lookup = {}

#     if os.path.exists(reddit_path):
#         for f in os.listdir(reddit_path):
#             if f.startswith("story_") and f.endswith(".json"):
#                 with open(os.path.join(reddit_path, f), encoding="utf-8") as jf:
#                     data = json.load(jf)
#                     idx = re.search(r"story_(\d+)", f).group(1)
#                     format_lookup[f"final_{idx}.mp4"] = {
#                         "title": data.get("title", f"story_{idx}"),
#                         "format": data.get("format", "?")
#                     }

#     uploaded = []
#     pending = []
#     for vid in all_videos:
#         info = format_lookup.get(vid, {"title": vid, "format": "?"})
#         if vid in uploaded_info:
#             link = uploaded_info[vid].get("url", "")
#             title = uploaded_info[vid].get("title", info["title"])
#             uploaded.append(f"[{info['format']}] [{title}](<{link}>)" if link else f"{title} [{info['format']}] ✅")
#         else:
#             pending.append(f"{info['title']} [{info['format']}]")

#     status = f"\n📅 {d}:\n"
#     status += f" 🎬 Uploaded:\n   • " + ("\n   • ".join(uploaded) if uploaded else "None") + "\n"
#     status += f" 🕒 Pending:\n   • " + ("\n   • ".join(pending) if pending else "None") + "\n"
#     status_report.append(status)

#     return "\n".join(status_report)


# if __name__ == "__main__":
#     print(torch.__version__)
#     print(torch.cuda.is_available())
