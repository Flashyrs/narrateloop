import os
import pickle
import re
from pathlib import Path
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
TOKEN_PATH = Path("token.pickle").resolve()

_cached_titles = None

def strip_part_suffix(title):
    return re.sub(r"\s*\[Part \d+ of \d+\]$", "", title, flags=re.IGNORECASE).strip().lower()

def get_authenticated_service():
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(f"🔐 Token file not found: {TOKEN_PATH}")
    with open(TOKEN_PATH, "rb") as token_file:
        creds = pickle.load(token_file)
    return build("youtube", "v3", credentials=creds)

def get_recent_video_titles(max_results=200):
    youtube = get_authenticated_service()
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
            raw_title = item["snippet"]["title"]
            titles.append(strip_part_suffix(raw_title))
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return titles

def is_title_already_uploaded(target_title):
    global _cached_titles
    if _cached_titles is None:
        print("🔄 Fetching recent uploaded titles from YouTube...")
        _cached_titles = get_recent_video_titles()
    return strip_part_suffix(target_title) in _cached_titles

