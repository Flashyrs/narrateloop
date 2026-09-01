import os
import sys
import json
import requests
import re
import html
import praw
from dotenv import load_dotenv
from datetime import datetime, timedelta
from utils.youtube_utils import is_title_already_uploaded
from utils.thumbnail_utils import capture_reddit_screenshot, create_fallback_thumbnail
from utils.title_utils import generate_title_with_gemini

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SUBREDDITS = [
     "AskReddit", 
    "TrueOffMyChest",
      "relationship_advice",
     "Karen", 
    "TIFU",
    "NuclearRevenge", "AmITheAsshole", "confessions"
    "AskRedditKpop"
    # "bangtan",
    # "bts7"
]

CENSOR_WORDS = ["fuck", "shit", "bitch", "asshole", "dick", "bastard", "crap", "cunt", "fag", "nigger"]

WORDS_PER_MINUTE = 150
MAX_VIDEO_WORDS = 1500
MIN_SHORT_WORDS = 225
MAX_SHORT_WORDS = 300

def censor(text):
    def replace_word(word):
        return re.sub(rf"\b{re.escape(word)}\b", word[0] + "*" * (len(word) - 1), flags=re.IGNORECASE, string=text)
    for word in CENSOR_WORDS:
        text = replace_word(word)
    return text

def split_story(text, max_words):
    words = text.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]

def get_or_create_thumbnail(post_url, title_text, body_text, save_path):
    success = capture_reddit_screenshot(post_url, save_path)
    if not success:
        print("⚠️ Screenshot failed — creating fallback thumbnail.")
        create_fallback_thumbnail(title_text, body_text, save_path)

def fetch_reddit_posts():
    posts_collected = []

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "android:com.narrateloop.shorts:v1.0 (by /u/Flashyrs)")

    # Method 1: Official PRAW API (Fast & Block-Free)
    if client_id and client_secret:
        try:
            print("🔑 Fetching Reddit posts via authenticated PRAW API...")
            praw_kwargs = {
                "client_id": client_id,
                "client_secret": client_secret,
                "user_agent": user_agent
            }
            username = os.getenv("REDDIT_USERNAME")
            password = os.getenv("REDDIT_PASSWORD")
            if username and password:
                praw_kwargs["username"] = username
                praw_kwargs["password"] = password

            reddit = praw.Reddit(**praw_kwargs)
            for subreddit_name in SUBREDDITS:
                try:
                    sub = reddit.subreddit(subreddit_name)
                    for post in sub.top(time_filter="day", limit=20):
                        if not post.selftext or len(post.selftext) < 100 or post.score < 50:
                            continue
                        posts_collected.append({
                            "title": censor(post.title.strip()),
                            "text": censor(post.selftext.strip()),
                            "score": post.score,
                            "subreddit": subreddit_name,
                            "permalink": post.permalink
                        })
                except Exception as sub_e:
                    print(f"⚠️ Failed to fetch r/{subreddit_name} via PRAW: {sub_e}")
                    continue
        except Exception as e:
            print(f"⚠️ PRAW initialization failed: {e}")

    # Method 1.5: Direct Reddit OAuth API Fallback (for Cloud Datacenter IPs)
    if not posts_collected and client_id and client_secret:
        proxies_list = [None, {"http": "socks5h://127.0.0.1:40000", "https": "socks5h://127.0.0.1:40000"}]
        for proxies in proxies_list:
            if posts_collected:
                break
            try:
                auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
                token_data = {"grant_type": "client_credentials"}
                username = os.getenv("REDDIT_USERNAME")
                password = os.getenv("REDDIT_PASSWORD")
                if username and password:
                    token_data = {
                        "grant_type": "password",
                        "username": username,
                        "password": password
                    }

                token_resp = requests.post(
                    "https://www.reddit.com/api/v1/access_token",
                    auth=auth,
                    data=token_data,
                    headers={"User-Agent": user_agent},
                    proxies=proxies,
                    timeout=10
                )
                if token_resp.status_code == 200:
                    access_token = token_resp.json().get("access_token")
                    oauth_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "User-Agent": user_agent
                    }
                    for subreddit_name in SUBREDDITS:
                        url = f"https://oauth.reddit.com/r/{subreddit_name}/top.json?limit=20&t=day&raw_json=1"
                        try:
                            res = requests.get(url, headers=oauth_headers, proxies=proxies, timeout=10)
                            if res.status_code == 200:
                                data_children = res.json().get("data", {}).get("children", [])
                                for child in data_children:
                                    pdata = child.get("data", {})
                                    selftext = pdata.get("selftext", "")
                                    score = pdata.get("score", 0)
                                    if not selftext or len(selftext) < 100 or score < 50:
                                        continue
                                    posts_collected.append({
                                        "title": censor(pdata.get("title", "").strip()),
                                        "text": censor(selftext.strip()),
                                        "score": score,
                                        "subreddit": subreddit_name,
                                        "permalink": pdata.get("permalink", "")
                                    })
                            else:
                                print(f"⚠️ Direct OAuth r/{subreddit_name} returned {res.status_code}")
                        except Exception as sub_e:
                            print(f"⚠️ Direct OAuth fetch failed for r/{subreddit_name}: {sub_e}")
                else:
                    print(f"⚠️ Access token request returned {token_resp.status_code}")
            except Exception as oauth_e:
                pass

    # Method 2: High-Speed RSS2JSON Fallback (100% Reliable on Cloud Servers)
    if not posts_collected:
        print("🌐 Fetching top stories via RSS2JSON feed parser...")
        for subreddit in SUBREDDITS:
            try:
                rss_url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"
                api_url = f"https://api.rss2json.com/v1/api.json?rss_url={requests.utils.quote(rss_url)}"
                res = requests.get(api_url, timeout=10)
                if res.status_code == 200:
                    feed_data = res.json()
                    for item in feed_data.get("items", []):
                        raw_desc = item.get("description", "") or item.get("content", "")
                        # Remove HTML markup and unescape HTML entities
                        clean_text = re.sub(r"<[^>]+>", " ", raw_desc)
                        clean_text = re.sub(r"submitted by\s+.*?to\s+r/\w+", "", clean_text, flags=re.IGNORECASE)
                        clean_text = re.sub(r"\[link\]\s+\[comments\]", "", clean_text, flags=re.IGNORECASE)
                        clean_text = html.unescape(clean_text).strip()
                        clean_text = re.sub(r"\s+", " ", clean_text)

                        if not clean_text or len(clean_text) < 100:
                            continue

                        posts_collected.append({
                            "title": censor(item.get("title", "").strip()),
                            "text": censor(clean_text),
                            "score": 500,  # Top daily posts
                            "subreddit": subreddit,
                            "permalink": item.get("link", "")
                        })
            except Exception as rss_e:
                print(f"⚠️ RSS2JSON fetch failed for r/{subreddit}: {rss_e}")

    # Method 3: Public JSON Fallback (if PRAW and RSS not available)
    if not posts_collected:
        print("🌐 Falling back to public JSON scraping...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        for subreddit in SUBREDDITS:
            url = f'https://www.reddit.com/r/{subreddit}/top.json?limit=15&t=day'
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    continue
                posts = res.json().get('data', {}).get('children', [])
                for post in posts:
                    data = post["data"]
                    if not data.get("selftext") or len(data["selftext"]) < 100:
                        continue
                    if data.get("score", 0) < 50:
                        continue
                    posts_collected.append({
                        "title": censor(data["title"].strip()),
                        "text": censor(data["selftext"].strip()),
                        "score": data.get("score", 0),
                        "subreddit": subreddit,
                        "permalink": data.get("permalink")
                    })
            except Exception as e:
                print(f"⚠️ Failed to fetch from r/{subreddit}: {e}")
                continue

    if not posts_collected:
        raise Exception("❌ No suitable posts found.")

    posts_collected.sort(key=lambda x: x["score"], reverse=True)

    # Configuration toggles from environment
    only_shorts = os.getenv("ONLY_SHORTS", "true").lower() in ("true", "1", "yes")
    target_shorts = int(os.getenv("TARGET_SHORTS_PER_DAY", "3"))
    target_videos = 0 if only_shorts else int(os.getenv("TARGET_VIDEOS_PER_DAY", "1"))

    shorts_collected = 0
    videos_collected = 0

    date_today = datetime.now()
    date_str_today = date_today.strftime("%Y%m%d")
    out_dir_today = os.path.join(PROJECT_ROOT, "reddit_stories", date_str_today)
    os.makedirs(out_dir_today, exist_ok=True)
    idx_today = 1

    for post in posts_collected:
        text = post["text"]
        word_count = len(text.split())
        raw_title = post["title"]
        subreddit = post["subreddit"]
        title_with_subreddit = f"[{subreddit}] {raw_title}"
        gemini_title = generate_title_with_gemini(text, title_with_subreddit)

        if is_title_already_uploaded(gemini_title):
            print(f"⏩ Skipping already uploaded: {gemini_title}")
            continue

        post_url = f"https://www.reddit.com{post['permalink']}"

        # ----- LONG VIDEO STORIES (Only if not in ONLY_SHORTS mode) -----
        if not only_shorts and word_count > 400 and videos_collected < target_videos:
            if word_count <= MAX_VIDEO_WORDS:
                if shorts_collected >= target_shorts:
                    # Save single-part video
                    story = {
                        "title": gemini_title,
                        "text": text,
                        "part": 1,
                        "total_parts": 1,
                        "format": "video"
                    }

                    story_path = os.path.join(out_dir_today, f"story_{idx_today}.json")
                    with open(story_path, "w", encoding="utf-8") as f:
                        json.dump(story, f, indent=4, ensure_ascii=False)

                    screenshot_path = os.path.join(out_dir_today, f"thumb_{idx_today}.png")
                    get_or_create_thumbnail(post_url, gemini_title, text, screenshot_path)

                    print(f"🎬 Saved video story: {story_path}")
                    idx_today += 1
                    videos_collected += 1

            else:
                # Split into multiple parts
                parts = split_story(text, MAX_VIDEO_WORDS)
                total_parts = len(parts)

                for i, part in enumerate(parts):
                    story = {
                        "title": f"{gemini_title} [Part {i+1} of {total_parts}]",
                        "text": part.strip(),
                        "part": i + 1,
                        "total_parts": total_parts,
                        "format": "video"
                    }

                    if i == 0 and shorts_collected >= target_shorts and videos_collected < target_videos:
                        story_path = os.path.join(out_dir_today, f"story_{idx_today}.json")
                        with open(story_path, "w", encoding="utf-8") as f:
                            json.dump(story, f, indent=4, ensure_ascii=False)

                        screenshot_path = os.path.join(out_dir_today, f"thumb_{idx_today}.png")
                        get_or_create_thumbnail(post_url, gemini_title, text, screenshot_path)

                        print(f"🎬 Saved multi-part video story (Part 1): {story_path}")
                        idx_today += 1
                        videos_collected += 1
                    else:
                        # Schedule future parts
                        future_date = date_today + timedelta(days=i)
                        future_str = future_date.strftime("%Y%m%d")
                        future_dir = os.path.join(PROJECT_ROOT, "reddit_stories", future_str)
                        os.makedirs(future_dir, exist_ok=True)
                        future_idx = len([f for f in os.listdir(future_dir) if f.startswith("story_")]) + 1
                        future_path = os.path.join(future_dir, f"story_{future_idx}.json")

                        with open(future_path, "w", encoding="utf-8") as f:
                            json.dump(story, f, indent=4, ensure_ascii=False)

                        print(f"📅 Scheduled Part {i+1} for {future_str}: {future_path}")

        # ----- SHORT STORIES -----
        elif shorts_collected < target_shorts:
            parts = split_story(text, MAX_SHORT_WORDS)
            min_words = int(os.getenv("MIN_SHORT_WORDS", str(MIN_SHORT_WORDS)))
            valid_parts = [p for p in parts if len(p.split()) >= min_words]
            if not valid_parts and len(text.split()) >= 80:
                valid_parts = [text]  # Accept slightly shorter stories if readable
            total_parts = len(valid_parts)

            for i, part in enumerate(valid_parts):
                if shorts_collected >= target_shorts:
                    break

                story = {
                    "title": f"{gemini_title} [Part {i+1} of {total_parts}]" if total_parts > 1 else gemini_title,
                    "text": part.strip(),
                    "part": i + 1,
                    "total_parts": total_parts,
                    "format": "short",
                    "subreddit": subreddit
                }

                story_path = os.path.join(out_dir_today, f"story_{idx_today}.json")
                with open(story_path, "w", encoding="utf-8") as f:
                    json.dump(story, f, indent=4, ensure_ascii=False)

                screenshot_path = os.path.join(out_dir_today, f"thumb_{idx_today}.png")
                get_or_create_thumbnail(post_url, gemini_title, part.strip(), screenshot_path)

                print(f"🎯 Saved short story: {story_path}")
                idx_today += 1
                shorts_collected += 1

        # ----- Exit condition -----
        if shorts_collected >= target_shorts and videos_collected >= target_videos:
            break

    if shorts_collected < target_shorts:
        raise Exception(f"❌ Not enough short stories collected (collected {shorts_collected}/{target_shorts}).")

    print(f"✅ Saved {idx_today - 1} stories for {date_str_today} (Shorts: {shorts_collected}, Videos: {videos_collected})")
    return date_str_today, idx_today - 1

if __name__ == "__main__":
    fetch_reddit_posts()

