import os
import time
import pickle
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

def upload_video(file_path, title, description, tags=None, thumbnail_path=None):
    youtube = authenticate_youtube(allow_interactive=False)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22"  # "People & Blogs"
        },
        "status": {
            "privacyStatus": "public",
            "containsSyntheticMedia": True
        }
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
    print(f"✅ Uploaded: {video_url}")
    return video_url

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Upload and Auth Utility")
    parser.add_argument("--auth", action="store_true", help="Run interactive OAuth authentication")
    parser.add_argument("--headless", action="store_true", help="Run OAuth in headless mode")
    parser.add_argument("--port", type=int, default=8080, help="Port for OAuth redirect server")
    args = parser.parse_args()

    if args.auth:
        authenticate_youtube(headless=args.headless, port=args.port, allow_interactive=True)
        print("🎉 Authentication successful!")

