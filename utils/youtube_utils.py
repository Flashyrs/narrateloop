import os
import pickle
import re
from pathlib import Path
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

TOKEN_PATH = Path("token.pickle").resolve()
CLIENT_SECRET = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json")).resolve()

_cached_titles = None

def strip_part_suffix(title):
    return re.sub(r"\s*\[Part \d+ of \d+\]$", "", title, flags=re.IGNORECASE).strip().lower()

def get_authenticated_service(allow_interactive=False):
    creds = None

    # Load existing token
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "rb") as token_file:
                creds = pickle.load(token_file)
        except Exception as e:
            print(f"⚠️ Error loading token from {TOKEN_PATH}: {e}")
            creds = None

    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
            print("🔁 Token refreshed successfully.")
        except Exception as e:
            print(f"⚠️ Refresh token failed: {e}. Token expired/revoked.")
            creds = None  # Force reauth

    # If no valid creds, check if interactive mode is explicitly allowed
    if not creds or not creds.valid:
        if not allow_interactive:
            # In automated background pipelines, NEVER block on local server!
            return None

        if not CLIENT_SECRET.exists():
            return None
        try:
            print("🔐 Attempting interactive OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
            with open(TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
            print("✅ Token saved to disk.")
        except Exception as e:
            print(f"⚠️ OAuth interactive flow skipped: {e}")
            return None

    if creds and creds.valid:
        try:
            return build("youtube", "v3", credentials=creds)
        except Exception as e:
            print(f"⚠️ Failed building YouTube client: {e}")
            return None
    return None

def get_recent_video_titles(max_results=200):
    global _cached_titles
    try:
        youtube = get_authenticated_service()
        if not youtube:
            _cached_titles = []
            return []
        titles = []
        next_page_token = None

        while len(titles) < max_results:
            request = youtube.search().list(
                part="snippet",
                forMine=True,
                type="video",
                maxResults=min(50, max_results - len(titles)),
                pageToken=next_page_token
            )
            response = request.execute()
            for item in response.get("items", []):
                snippet = item.get("snippet")
                if isinstance(snippet, dict):
                    raw_title = snippet.get("title", "")
                    if raw_title:
                        titles.append(strip_part_suffix(raw_title))
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        _cached_titles = titles
        return titles
    except Exception as e:
        print(f"⚠️ Warning fetching YouTube titles (using fallback): {e}")
        _cached_titles = []
        return []

def is_title_already_uploaded(target_title):
    global _cached_titles
    if not target_title:
        return False
    try:
        if _cached_titles is None:
            print("🔄 Fetching recent uploaded titles from YouTube...")
            _cached_titles = get_recent_video_titles()
        return strip_part_suffix(target_title) in (_cached_titles or [])
    except Exception:
        return False

def get_youtube_auth_url(redirect_uri="http://localhost"):
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(f"client_secret.json not found at {CLIENT_SECRET}")
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube"
        ],
        redirect_uri=redirect_uri
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return auth_url

def finish_youtube_auth_flow(code_or_url, redirect_uri="http://localhost"):
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(f"client_secret.json not found at {CLIENT_SECRET}")

    code = code_or_url.strip()
    if "code=" in code:
        import urllib.parse
        parsed = urllib.parse.urlparse(code)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            code = params["code"][0]
        else:
            m = re.search(r"code=([^&]+)", code)
            if m:
                code = urllib.parse.unquote(m.group(1))

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube"
        ],
        redirect_uri=redirect_uri
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, "wb") as token_file:
        pickle.dump(creds, token_file)

    channel_name = "Unknown Channel"
    try:
        service = build("youtube", "v3", credentials=creds)
        res = service.channels().list(part="snippet", mine=True).execute()
        items = res.get("items", [])
        if items:
            channel_name = items[0].get("snippet", {}).get("title", channel_name)
    except Exception as e:
        print(f"⚠️ Warning fetching channel details: {e}")

    return channel_name

def get_youtube_auth_status():
    if not TOKEN_PATH.exists():
        return {
            "status": "missing",
            "message": "❌ No token.pickle found. Use /auth_youtube to connect your channel."
        }
    try:
        with open(TOKEN_PATH, "rb") as token_file:
            creds = pickle.load(token_file)
    except Exception as e:
        return {
            "status": "corrupt",
            "message": f"❌ token.pickle corrupt: {e}. Use /auth_youtube to re-authenticate."
        }

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
        except Exception as e:
            return {
                "status": "expired",
                "message": f"⚠️ Refresh token expired or revoked ({e}). Use /auth_youtube to re-authenticate."
            }

    if creds and creds.valid:
        channel_name = "Connected Channel"
        try:
            service = build("youtube", "v3", credentials=creds)
            res = service.channels().list(part="snippet", mine=True).execute()
            items = res.get("items", [])
            if items:
                channel_name = items[0].get("snippet", {}).get("title", channel_name)
        except Exception:
            pass
        return {
            "status": "valid",
            "message": f"✅ YouTube connection active.\n📺 Channel: <b>{channel_name}</b>\n🔑 Status: Ready for automated uploads."
        }

    return {
        "status": "invalid",
        "message": "⚠️ Token is invalid. Use /auth_youtube to connect your channel."
    }
