import os
import json
from datetime import datetime
from scripts.upload_to_youtube import upload_video, generate_title_and_description

def upload_pending_video():
    date_str = datetime.now().strftime("%Y%m%d")
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
        if video_file in already_uploaded:
            continue

        video_path = os.path.join(output_dir, video_file)
        story_path = os.path.join(reddit_dir, f"story_{i}.json")
        if not os.path.exists(video_path) or not os.path.exists(story_path):
            continue

        with open(story_path, "r", encoding="utf-8") as f:
            story = json.load(f)

        title, description, tags = generate_title_and_description(story)
        url = upload_video(video_path, title, description, tags=tags)
        with open(uploaded_log, "a") as f:
            f.write(video_file + "\n")
        return f"Uploaded {video_file}\n{url}"

    return "No pending videos to upload."
