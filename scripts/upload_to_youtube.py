import os
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
        hashtags = "#shorts #redditstories #aita #askreddit #storytime #NarrateLoop #funny #minecraftshorts #relatable"
        title = f"{base_title} #shorts"
        tags = ["shorts", "reddit", "minecraft", "story", "storytime"]
    else:
        hashtags = "#redditstories #aita #askreddit #storytime #NarrateLoop #redditvideos #youtubevideo #relatable"
        title = base_title
        tags = ["reddit", "storytime", "aita", "youtubevideo", "redditstories"]

    title = title[:100]
    description = (
        f"{base_title}\n\n"
        f"{short_description}\n\n"
        f"Subscribe to my Channel 👉 https://www.youtube.com/@NarrateLoop\n\n"
        f"{hashtags}"
    )
    return title, description[:4900], tags

def authenticate_youtube():
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]
    creds = None
    token_path = "token.pickle"
    client_secret = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json")).resolve()

    if not os.path.exists(client_secret):
        raise FileNotFoundError(f"client_secret.json not found at {client_secret}")

    # Load credentials if token exists
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

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

    # If no creds or refresh failed, authenticate again
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
        print("🆕 New token generated and saved.")

    return build("youtube", "v3", credentials=creds)

def upload_video(file_path, title, description, tags=None, thumbnail_path=None):
    youtube = authenticate_youtube()

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22"  # "People & Blogs"
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    media = MediaFileUpload(file_path)

    response = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    ).execute()

    if thumbnail_path and os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=response["id"],
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()

    video_url = f"https://youtube.com/watch?v={response['id']}"
    print(f"✅ Uploaded: {video_url}")
    return video_url




# import os
# import pickle
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload
# from google_auth_oauthlib.flow import InstalledAppFlow
# from pathlib import Path


# def generate_title_and_description(story):
#     base_title = story['title'].strip()
#     format_type = story.get("format", "short")  # fallback to short if missing
#     short_description = story.get("text", "").strip().replace("\n", " ")[:200]

#     if format_type == "short":
#         hashtags = "#shorts #redditstories #aita #askreddit #storytime #NarrateLoop #funny #minecraftshorts #relatable"
#         title = f"{base_title} #shorts"
#         tags = ["shorts", "reddit", "minecraft", "story", "storytime"]
#     else:
#         hashtags = "#redditstories #aita #askreddit #storytime #NarrateLoop #redditvideos #youtubevideo #relatable"
#         title = base_title
#         tags = ["reddit", "storytime", "aita", "youtubevideo", "redditstories"]

#     title = title[:100]  # YouTube title limit

#     # ✨ New description with subscribe line
#     description = (
#         f"{base_title}\n\n"
#         f"{short_description}\n\n"
#         f"Subscribe to my Channel 👉 https://www.youtube.com/@NarrateLoop\n\n"
#         f"{hashtags}"
#     )

#     return title, description[:4900], tags



# def authenticate_youtube():
#     SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
#               "https://www.googleapis.com/auth/youtube.readonly"]
#     creds = None
#     token_path = "token.pickle"

#     base_dir = os.path.abspath(os.path.dirname(__file__))
#     client_secret = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json")).resolve()

#     if not os.path.exists(client_secret):
#         raise FileNotFoundError(f"client_secret.json not found at {client_secret}")

#     if os.path.exists(token_path):
#         with open(token_path, "rb") as token:
#             creds = pickle.load(token)
#     else:
#         flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
#         creds = flow.run_local_server(port=0)
#         with open(token_path, "wb") as token:
#             pickle.dump(creds, token)

#     return build("youtube", "v3", credentials=creds)


# def upload_video(file_path, title, description, tags=None):
#     youtube = authenticate_youtube()

#     request_body = {
#         "snippet": {
#             "title": title,
#             "description": description,
#             "tags": tags or [],
#             "categoryId": "22"  # People & Blogs
#         },
#         "status": {
#             "privacyStatus": "public"
#         }
#     }

#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"Video file not found: {file_path}")

#     media = MediaFileUpload(file_path)

#     response = youtube.videos().insert(
#         part="snippet,status",
#         body=request_body,
#         media_body=media
#     ).execute()

#     video_url = f"https://youtube.com/watch?v={response['id']}"
#     print(f" Uploaded: {video_url}")
#     return video_url
