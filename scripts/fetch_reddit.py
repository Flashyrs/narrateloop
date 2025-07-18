import os
import json
import requests
import re
from datetime import datetime, timedelta
from utils.youtube_utils import is_title_already_uploaded
from utils.thumbnail_utils import capture_reddit_screenshot, create_fallback_thumbnail
from utils.title_utils import generate_title_with_gemini

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SUBREDDITS = [
    # "AskReddit", "TrueOffMyChest",
    #  "relationship_advice",
    # #  "Karen", "TIFU",
    # "NuclearRevenge", "AmITheAsshole", "confessions"
    "kpop",
    "bangtan",
    "bts7"
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
    headers = {'User-Agent': 'RedditYTBot/1.0'}
    posts_collected = []

    for subreddit in SUBREDDITS:
        url = f'https://www.reddit.com/r/{subreddit}/top.json?limit=10&t=day'
        try:
            res = requests.get(url, headers=headers, timeout=10)
            posts = res.json().get('data', {}).get('children', [])
            for post in posts:
                data = post["data"]
                if not data.get("selftext") or len(data["selftext"]) < 100:
                    continue
                if data.get("score", 0) < 100:
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

        # ----- VIDEO STORIES -----
        if word_count > 400:
            if word_count <= MAX_VIDEO_WORDS:
                if shorts_collected >= 3 and videos_collected < 1:
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

                    if i == 0 and shorts_collected >= 3 and videos_collected < 1:
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
        elif shorts_collected < 3:
            parts = split_story(text, MAX_SHORT_WORDS)
            valid_parts = [p for p in parts if len(p.split()) >= MIN_SHORT_WORDS]
            total_parts = len(valid_parts)

            for i, part in enumerate(valid_parts):
                if shorts_collected >= 3:
                    break

                story = {
                    "title": f"{gemini_title} [Part {i+1} of {total_parts}]" if total_parts > 1 else gemini_title,
                    "text": part.strip(),
                    "part": i + 1,
                    "total_parts": total_parts,
                    "format": "short"
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
        if shorts_collected >= 3 and videos_collected >= 1:
            break


    if shorts_collected < 3:
        raise Exception("❌ Not enough short stories collected.")

    print(f"✅ Saved {idx_today - 1} stories for {date_str_today}")
    return date_str_today, idx_today - 1

if __name__ == "__main__":
    fetch_reddit_posts()

