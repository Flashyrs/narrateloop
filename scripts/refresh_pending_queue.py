# scripts/refresh_pending_queue.py

import os

# Get project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Absolute paths
GAMEPLAY_DIR = os.path.join(PROJECT_ROOT, "assets", "gameplays")
QUEUE_FILE = os.path.join(PROJECT_ROOT, "queue", "pending.txt")

def refresh_pending_queue():
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)

    all_clips = [
        f.replace(".mp4", "")
        for f in os.listdir(GAMEPLAY_DIR)
        if f.endswith(".mp4")
    ]

    # Read already used clips
    used_clips = set()
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            used_clips.update(line.strip() for line in f.readlines())

    # Filter out already queued clips
    new_clips = [clip for clip in all_clips if clip not in used_clips]

    if not new_clips:
        print(" No new gameplay clips to add.")
        return

    with open(QUEUE_FILE, "a") as f:
        for clip in new_clips:
            f.write(clip + "\n")

    print(f" Added {len(new_clips)} new clips to {QUEUE_FILE}")

if __name__ == "__main__":
    refresh_pending_queue()
