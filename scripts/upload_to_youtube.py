import os
import time
import pickle
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def parse_schedule_time(time_input, default_tz_name=None):
    """
    Parses various date/time input formats into an RFC 3339 / ISO 8601 UTC string
    required by YouTube Data API (e.g., '2026-11-07T12:30:00Z').
    
    Accepts:
    - datetime object
    - ISO 8601 string: '2026-11-07T18:00:00Z'
    - Relative hours: '+24h', '+1d'
    - 'tomorrow HH:MM': e.g., 'tomorrow 18:00'
    - Date string: '2026-11-07 18:00'
    """
    if not time_input:
        return None

    if isinstance(time_input, datetime):
        if time_input.tzinfo is None:
            time_input = time_input.replace(tzinfo=timezone.utc)
        return time_input.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = str(time_input).strip()

    # If already UTC ISO format with Z
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", raw):
        return raw

    # Determine local timezone
    tz = timezone.utc
    tz_name = default_tz_name or os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        pass

    now = datetime.now(tz)

    # Handle relative: +Xh or +Xd
    rel_match = re.match(r"^\+(\d+)\s*(h|hr|hours?|d|days?)$", raw, re.IGNORECASE)
    if rel_match:
        val = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        delta = timedelta(days=val) if unit.startswith("d") else timedelta(hours=val)
        target = now + delta
        return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Handle 'tomorrow [HH:MM]'
    if raw.lower().startswith("tomorrow"):
        time_part = raw[8:].strip() or "18:00"
        try:
            hour, minute = map(int, time_part.split(":"))
        except Exception:
            hour, minute = 18, 0
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Handle 'today [HH:MM]'
    if raw.lower().startswith("today"):
        time_part = raw[5:].strip() or "18:00"
        try:
            hour, minute = map(int, time_part.split(":"))
        except Exception:
            hour, minute = 18, 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Handle standard YYYY-MM-DD HH:MM or YYYY-MM-DDTHH:MM:SS
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            target = dt.replace(tzinfo=tz)
            return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    raise ValueError(
        f"Unrecognized schedule time format: '{raw}'. "
        "Use ISO format (e.g. '2026-11-07T18:00:00Z'), 'tomorrow 18:00', or '+24h'."
    )

def generate_title_and_description(story):
    base_title = story["title"].strip()[:100]
    format_type = story.get("format", "short").strip().lower()
    short_description = story.get("text", "").strip().replace("\n", " ")[:200]

    if format_type == "short":
        hashtags = "#shorts #psychology #casestudy #behavioralanalysis #storytime #relationshipadvice #NarrateLoop"
        title = f"{base_title} #shorts"
        tags = ["shorts", "psychology", "behavioral analysis", "case study", "storytime", "relationships", "dilemma"]
    else:
        hashtags = "#psychology #casestudy #behavioralanalysis #storytime #relationshipadvice #NarrateLoop #deepdive"
        title = base_title
        tags = ["psychology", "behavioral analysis", "case study", "storytime", "relationships", "reddit analysis"]

    title = title[:100]
    description = (
        f"{base_title}\n\n"
        f"{short_description}\n\n"
        f"Subscribe to my Channel 👉 https://www.youtube.com/@NarrateLoop\n\n"
        f"{hashtags}"
    )
    return title, description[:4900], tags

def authenticate_youtube(headless=False, port=8080, allow_interactive=False):
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube"
    ]
    creds = None
    project_root = Path(__file__).resolve().parent.parent
    token_path = Path(os.getenv("YOUTUBE_TOKEN_PATH", project_root / "token.pickle")).resolve()
    client_secret = Path(os.getenv("YOUTUBE_CLIENT_SECRET", project_root / "client_secret.json")).resolve()

    # Load credentials if token exists
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"[WARNING] Failed reading token file: {e}")
            creds = None

    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "wb") as token:
                pickle.dump(creds, token)
            print("🔁 Token refreshed and saved.")
        except Exception as e:
            print(f"[ERROR] Token refresh failed: {e}")
            creds = None

    # If no valid creds
    if not creds or not creds.valid:
        if not allow_interactive:
            raise RuntimeError(
                "YouTube token is missing or expired. "
                "Run 'python scripts/upload_to_youtube.py --auth' interactively to authenticate."
            )

        if not os.path.exists(client_secret):
            raise FileNotFoundError(f"client_secret.json not found at {client_secret}")

        flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
        print("🔑 Initiating OAuth authentication...")
        if headless:
            print(f"⚠️ Headless mode enabled. Ensure port {port} is forwarded or accessible.")
        creds = flow.run_local_server(port=port, open_browser=not headless)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
        print("🆕 New token generated and saved.")

    return build("youtube", "v3", credentials=creds)

def upload_video(file_path, title, description, tags=None, thumbnail_path=None, publish_at=None):
    youtube = authenticate_youtube(allow_interactive=False)

    status_body = {
        "containsSyntheticMedia": True
    }

    if publish_at:
        publish_utc_str = parse_schedule_time(publish_at)
        # YouTube requires privacyStatus to be 'private' for scheduled uploads
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_utc_str
        print(f"🕒 Video scheduled to publish at: {publish_utc_str} (UTC)")
    else:
        status_body["privacyStatus"] = "public"

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22"  # "People & Blogs"
        },
        "status": status_body
    }

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    response = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    ).execute()

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            time.sleep(3)  # Brief delay to allow YouTube video processing initialization
            mime_type = "image/png" if str(thumbnail_path).lower().endswith(".png") else "image/jpeg"
            thumb_media = MediaFileUpload(thumbnail_path, mimetype=mime_type, resumable=False)
            youtube.thumbnails().set(
                videoId=response["id"],
                media_body=thumb_media
            ).execute()
            print(f"🖼️ Custom thumbnail set successfully ({thumbnail_path}).")
        except Exception as te:
            print(f"⚠️ Custom thumbnail upload failed ({te})")

    video_url = f"https://youtube.com/watch?v={response['id']}"
    if publish_at:
        print(f"✅ Video uploaded and scheduled! URL: {video_url}")
    else:
        print(f"✅ Uploaded (Public): {video_url}")
    return video_url

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Upload and Auth Utility")
    parser.add_argument("--auth", action="store_true", help="Run interactive OAuth authentication")
    parser.add_argument("--headless", action="store_true", help="Run OAuth in headless mode")
    parser.add_argument("--port", type=int, default=8080, help="Port for OAuth redirect server")
    parser.add_argument("--file", "-f", type=str, help="Path to video file to upload")
    parser.add_argument("--title", "-t", type=str, help="Video title")
    parser.add_argument("--description", "-d", type=str, default="", help="Video description")
    parser.add_argument("--tags", type=str, default="", help="Comma-separated video tags")
    parser.add_argument("--thumbnail", type=str, help="Path to thumbnail image")
    parser.add_argument("--schedule", "-s", type=str, help="Schedule time: e.g. 'tomorrow 18:00', '+24h', or ISO timestamp")
    args = parser.parse_args()

    if args.auth:
        authenticate_youtube(headless=args.headless, port=args.port, allow_interactive=True)
        print("🎉 Authentication successful!")
    elif args.file:
        video_tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        video_title = args.title or Path(args.file).stem
        upload_video(
            file_path=args.file,
            title=video_title,
            description=args.description,
            tags=video_tags,
            thumbnail_path=args.thumbnail,
            publish_at=args.schedule
        )

