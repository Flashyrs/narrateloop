import os
import json
import subprocess
from datetime import datetime, timedelta
from scripts.upload_to_youtube import upload_video, generate_title_and_description, parse_schedule_time

def get_current_time():
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()

def upload_pending_video():
    date_str = get_current_time().strftime("%Y%m%d")
    output_dir = os.path.join("output", date_str)
    reddit_dir = os.path.join("reddit_stories", date_str)
    uploaded_log = os.path.join(output_dir, "uploaded.txt")

    os.makedirs(output_dir, exist_ok=True)

    already_uploaded = []
    if os.path.exists(uploaded_log):
        with open(uploaded_log, "r") as f:
            already_uploaded = f.read().splitlines()

    for i in range(1, 4):
        video_file = f"final_{i}.mp4"
        if any(video_file in line for line in already_uploaded):
            continue

        video_path = os.path.join(output_dir, video_file)
        story_path = os.path.join(reddit_dir, f"story_{i}.json")
        if not os.path.exists(video_path) or not os.path.exists(story_path):
            continue

        # Sanity check with ffprobe
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            dur = float(probe.stdout.strip())
            if dur < 3.0:
                print(f"[Upload] Skipping {video_file}: corrupted or too short ({dur}s).")
                continue
        except Exception:
            continue

        with open(story_path, "r", encoding="utf-8") as f:
            story = json.load(f)

        title, description, tags = generate_title_and_description(story)
        thumb_path = os.path.join(reddit_dir, f"thumb_{i}.png")

        publish_at = None
        target_display = None
        if os.getenv("SCHEDULE_UPLOADS", "true").lower() in ("true", "1", "yes"):
            days_ahead = int(os.getenv("SCHEDULE_DAYS_AHEAD", "1"))
            # Default slot mapping: 2 -> 10:00, 3 -> 16:00, 1 -> 21:00
            slot_map = {2: "10:00", 3: "16:00", 1: "21:00"}
            slot_time = slot_map.get(i, "18:00")
            target_dt = get_current_time() + timedelta(days=days_ahead)
            target_str = f"{target_dt.strftime('%Y-%m-%d')} {slot_time}"
            publish_at = parse_schedule_time(target_str)
            target_display = f"{target_str} ({os.getenv('TIMEZONE', 'Asia/Kolkata')})"

        url = upload_video(
            video_path,
            title,
            description,
            tags=tags,
            thumbnail_path=thumb_path if os.path.exists(thumb_path) else None,
            publish_at=publish_at
        )
        entry = f"{video_file} | {title} | {url}"
        if target_display:
            entry += f" | Scheduled: {target_display}"
        with open(uploaded_log, "a") as f:
            f.write(entry + "\n")
        
        status_msg = f"Uploaded {video_file}\n{url}"
        if target_display:
            status_msg += f"\nScheduled for: {target_display}"
        return status_msg

    return "No pending videos to upload."
