import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import random
import requests
import re
import html
import hashlib
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from datetime import datetime
from utils.youtube_utils import is_title_already_uploaded
from utils.thumbnail_utils import create_reddit_thumbnail
from utils.title_utils import generate_title_with_gemini, enhance_story_hook_with_gemini

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

def get_current_time():
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()

# Curated list of engaging story subreddits
DEFAULT_SUBREDDITS = [
    "AITAH",
    "pettyrevenge",
    "confessions",
    "maliciouscompliance",
    "relationship_advice",
    "TrueOffMyChest",
    "tifu",
    "AmItheAsshole",
    "NuclearRevenge",
    "ProRevenge",
    "entitledparents",
    "EntitledPeople",
    "Stories",
    "offmychest"
]

env_subreddits = os.getenv("SUBREDDITS")
if env_subreddits:
    SUBREDDITS = [s.strip() for s in env_subreddits.split(",") if s.strip()]
else:
    SUBREDDITS = DEFAULT_SUBREDDITS

CENSOR_WORDS = ["fuck", "shit", "bitch", "asshole", "dick", "bastard", "crap", "cunt", "fag", "nigger"]

WORDS_PER_MINUTE = 150
MAX_VIDEO_WORDS = 1500
MIN_SHORT_WORDS = 100
MAX_SHORT_WORDS = 550

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0"
]

def strip_links_and_urls(text):
    if not text:
        return ""
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\bwww\.[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=]+', '', text)
    text = re.sub(r'(?i)\b(original\s+post|source\s+link|source|post\s+link|reddit\s+link|link|update)\s*:\s*', '', text)
    text = re.sub(r'(?i)\b(submitted\s+by|posted\s+by)\b.*', '', text)
    text = re.sub(r'(?i)\[link\]\s*\[comments\].*', '', text)
    text = re.sub(r'(?i)\b/?u/\w+\b', '', text)
    text = text.replace(r'\_', '_')
    text = re.sub(r'\s+([,.:;?!])', r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def censor(text):
    text = strip_links_and_urls(text)
    def replace_word(word):
        return re.sub(rf"\b{re.escape(word)}\b", word[0] + "*" * (len(word) - 1), flags=re.IGNORECASE, string=text)
    for word in CENSOR_WORDS:
        text = replace_word(word)
    return text

CTA_ENDINGS = [
    "What would you do in this situation? Let me know in the comments below, and subscribe for daily stories!",
    "Who do you think was in the wrong here? Drop your thoughts in the comments and subscribe for more stories!",
    "Would you have handled this differently? Let me know in the comments below, and subscribe for daily Reddit stories!"
]

def append_engagement_cta(text):
    if not text:
        return text
    clean = text.strip()
    if any(q in clean.lower()[-120:] for q in ["what would you do", "aita", "what do you think", "thoughts?", "let me know", "subscribe"]):
        return clean
    cta = random.choice(CTA_ENDINGS)
    return f"{clean} {cta}"

def trim_story_to_short(text, min_words=100, max_words=550):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    accumulated = []
    current_word_count = 0

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        words_in_s = len(s.split())
        if current_word_count + words_in_s <= max_words:
            accumulated.append(s)
            current_word_count += words_in_s
        else:
            if current_word_count >= min_words:
                break
            if current_word_count + words_in_s <= max_words + 30:
                accumulated.append(s)
                current_word_count += words_in_s
            break

    result = " ".join(accumulated).strip()
    return result, len(result.split())

def get_or_create_thumbnail(post_url, title_text, body_text, save_path, subreddit="relationship_advice", format="short"):
    create_reddit_thumbnail(
        title_text=title_text,
        subreddit=subreddit,
        body_text=body_text,
        output_path=save_path,
        format=format,
        post_url=post_url
    )

# --- Persistent Deduplication Memory ---
USED_POSTS_FILE = os.path.join(PROJECT_ROOT, "reddit_stories", "used_posts_history.json")

def load_used_posts_db():
    db = {
        "post_ids": [],
        "permalinks": [],
        "text_hashes": [],
        "records": []
    }
    
    if os.path.exists(USED_POSTS_FILE):
        try:
            with open(USED_POSTS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    db["post_ids"] = loaded.get("post_ids", [])
                    db["permalinks"] = loaded.get("permalinks", [])
                    db["text_hashes"] = loaded.get("text_hashes", [])
                    db["records"] = loaded.get("records", [])
        except Exception as e:
            print(f"⚠️ Warning loading used posts db: {e}")

    # Backfill from existing folders on disk
    reddit_stories_dir = os.path.join(PROJECT_ROOT, "reddit_stories")
    if os.path.exists(reddit_stories_dir):
        for entry in os.listdir(reddit_stories_dir):
            day_dir = os.path.join(reddit_stories_dir, entry)
            if os.path.isdir(day_dir) and re.match(r"^\d{8}$", entry):
                for sf in os.listdir(day_dir):
                    if sf.startswith("story_") and sf.endswith(".json"):
                        try:
                            with open(os.path.join(day_dir, sf), "r", encoding="utf-8") as jf:
                                sdata = json.load(jf)
                                stext = sdata.get("text", "")
                                if stext:
                                    thash = hashlib.md5(stext[:120].strip().encode("utf-8")).hexdigest()
                                    if thash not in db["text_hashes"]:
                                        db["text_hashes"].append(thash)
                                        db["records"].append({
                                            "date": entry,
                                            "title": sdata.get("title", ""),
                                            "subreddit": sdata.get("subreddit", ""),
                                            "text_hash": thash
                                        })
                        except Exception:
                            pass

    return db

def save_used_posts_db(db):
    os.makedirs(os.path.dirname(USED_POSTS_FILE), exist_ok=True)
    try:
        with open(USED_POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Warning saving used posts db: {e}")

def is_post_duplicate(post, used_db):
    permalink = post.get("permalink", "").strip()
    post_id = post.get("id", "")
    if not post_id and permalink:
        m = re.search(r"/comments/([a-z0-9]+)/", permalink)
        if m:
            post_id = m.group(1)

    if post_id and post_id in used_db.get("post_ids", []):
        return True

    if permalink and permalink in used_db.get("permalinks", []):
        return True

    raw_text = post.get("text", "")
    if raw_text:
        thash = hashlib.md5(raw_text[:120].strip().encode("utf-8")).hexdigest()
        if thash in used_db.get("text_hashes", []):
            return True

    raw_title = post.get("title", "")
    if raw_title and is_title_already_uploaded(raw_title):
        return True

    return False

def record_used_post(post, date_str, final_title, used_db):
    permalink = post.get("permalink", "").strip()
    post_id = post.get("id", "")
    if not post_id and permalink:
        m = re.search(r"/comments/([a-z0-9]+)/", permalink)
        if m:
            post_id = m.group(1)

    raw_text = post.get("text", "")
    thash = hashlib.md5(raw_text[:120].strip().encode("utf-8")).hexdigest() if raw_text else ""

    if post_id and post_id not in used_db["post_ids"]:
        used_db["post_ids"].append(post_id)
    if permalink and permalink not in used_db["permalinks"]:
        used_db["permalinks"].append(permalink)
    if thash and thash not in used_db["text_hashes"]:
        used_db["text_hashes"].append(thash)

    used_db["records"].append({
        "date": date_str,
        "post_id": post_id,
        "permalink": permalink,
        "subreddit": post.get("subreddit", ""),
        "title": final_title,
        "text_hash": thash
    })
    save_used_posts_db(used_db)

# --- Direct Reddit RSS Extraction Engine ---
def parse_reddit_rss_xml(xml_content, default_sub=""):
    posts = []
    try:
        root = ET.fromstring(xml_content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns) or root.findall('entry')
        for entry in entries:
            title_elem = entry.find('atom:title', ns) if ns else entry.find('title')
            title = title_elem.text if title_elem is not None else ""

            link_elem = entry.find('atom:link', ns) if ns else entry.find('link')
            link = link_elem.get('href', '') if link_elem is not None else ""

            id_elem = entry.find('atom:id', ns) if ns else entry.find('id')
            post_id = id_elem.text if id_elem is not None else ""

            cat_elem = entry.find('atom:category', ns) if ns else entry.find('category')
            sub = cat_elem.get('term', default_sub) if cat_elem is not None else default_sub

            content_elem = entry.find('atom:content', ns) if ns else entry.find('content')
            raw_html = content_elem.text if content_elem is not None else ""

            clean_text = re.sub(r'<[^>]+>', ' ', raw_html)
            clean_text = html.unescape(clean_text)
            clean_text = re.sub(r'(?i)\b(submitted\s+by|posted\s+by)\b.*', '', clean_text)
            clean_text = re.sub(r'(?i)\[link\]\s*\[comments\].*', '', clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()

            if clean_text and len(clean_text) >= 120:
                posts.append({
                    "id": post_id,
                    "title": censor(title.strip()),
                    "text": censor(clean_text),
                    "score": 500,
                    "subreddit": sub,
                    "permalink": link
                })
    except Exception as e:
        print(f"⚠️ RSS XML parse warning: {e}")
    return posts

def fetch_reddit_posts(target_date=None, replace_story_idx=None):
    posts_collected = []
    used_db = load_used_posts_db()
    print(f"📚 Loaded {len(used_db.get('records', []))} previously used posts from persistent history db.")

    date_today = get_current_time()
    date_str_today = target_date if target_date else date_today.strftime("%Y%m%d")
    out_dir_today = os.path.join(PROJECT_ROOT, "reddit_stories", date_str_today)
    os.makedirs(out_dir_today, exist_ok=True)

    # Check which subreddits are already used today
    used_subreddits_today = set()
    for sf in os.listdir(out_dir_today):
        if sf.startswith("story_") and sf.endswith(".json"):
            if replace_story_idx and sf == f"story_{replace_story_idx}.json":
                continue
            try:
                with open(os.path.join(out_dir_today, sf), "r", encoding="utf-8") as jf:
                    sdata = json.load(jf)
                    if sdata.get("subreddit"):
                        used_subreddits_today.add(sdata["subreddit"].lower())
            except Exception:
                pass

    print(f"📌 Subreddits already active today ({date_str_today}): {list(used_subreddits_today)}")

    # Method 1: Direct Reddit Multi-Feed RSS (Fastest & 100% Reliable)
    # Group subreddits into batches of 3-4 for rich variety in single HTTP calls
    subreddits_pool = list(SUBREDDITS)
    random.shuffle(subreddits_pool)

    # Prioritize subreddits not used today
    unused_pool = [s for s in subreddits_pool if s.lower() not in used_subreddits_today]
    if not unused_pool:
        unused_pool = subreddits_pool

    batches = [unused_pool[i:i + 4] for i in range(0, len(unused_pool), 4)]
    
    print("📡 Fetching stories via Direct Reddit RSS...")
    for batch in batches:
        multi_sub = "+".join(batch)
        urls = [
            f"https://www.reddit.com/r/{multi_sub}/top/.rss?t=day",
            f"https://www.reddit.com/r/{multi_sub}/hot/.rss"
        ]
        for url in urls:
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200 and len(res.text) > 1000:
                    parsed = parse_reddit_rss_xml(res.text)
                    for candidate in parsed:
                        if not is_post_duplicate(candidate, used_db):
                            # Avoid duplicates within current collection
                            if not any(p.get("permalink") == candidate["permalink"] for p in posts_collected):
                                posts_collected.append(candidate)
                        else:
                            print(f"🔁 [Deduplication] Skipped already-used post: {candidate['title'][:40]}...")
            except Exception as e:
                print(f"⚠️ RSS fetch warning for r/{multi_sub}: {e}")

        if len(posts_collected) >= 10:
            break

    # Method 2: Individual Subreddit RSS Fallback
    if len(posts_collected) < 3:
        print("🌐 Trying individual subreddit RSS feeds...")
        for sub in unused_pool:
            if len(posts_collected) >= 10:
                break
            url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
            try:
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code == 200 and len(res.text) > 1000:
                    parsed = parse_reddit_rss_xml(res.text, default_sub=sub)
                    for candidate in parsed:
                        if not is_post_duplicate(candidate, used_db):
                            if not any(p.get("permalink") == candidate["permalink"] for p in posts_collected):
                                posts_collected.append(candidate)
            except Exception:
                pass

    if not posts_collected:
        raise Exception("❌ No fresh, unseen posts found across all subreddits.")

    print(f"✨ Found {len(posts_collected)} fresh, unseen candidate posts!")

    # Subreddit Diversity Strategy: Select unique subreddits not used today
    selected_posts = []
    current_selected_subs = set(used_subreddits_today)

    for post in posts_collected:
        sub = post["subreddit"].lower()
        if sub not in current_selected_subs:
            selected_posts.append(post)
            current_selected_subs.add(sub)
            if replace_story_idx and len(selected_posts) >= 1:
                break
            elif not replace_story_idx and len(selected_posts) >= 3:
                break

    # If fewer than required unique subreddits, fill remaining from available candidates
    needed = 1 if replace_story_idx else 3
    if len(selected_posts) < needed:
        for post in posts_collected:
            if post not in selected_posts:
                selected_posts.append(post)
                if len(selected_posts) >= needed:
                    break

    # Determine which story index to save
    if replace_story_idx:
        indices_to_populate = [int(replace_story_idx)]
    else:
        indices_to_populate = [1, 2, 3]

    shorts_collected = 0

    for post in selected_posts:
        if not indices_to_populate:
            break

        idx_today = indices_to_populate.pop(0)
        raw_text = post["text"]
        subreddit = post["subreddit"]

        # AI Hook Transformation: rewrite opening 1-2 sentences for uniqueness & high CTR
        text = enhance_story_hook_with_gemini(raw_text, subreddit=subreddit)
        word_count = len(text.split())
        raw_title = post["title"]
        title_with_subreddit = f"[{subreddit}] {raw_title}"
        gemini_title = generate_title_with_gemini(text, title_with_subreddit)

        raw_permalink = post.get("permalink", "")
        post_url = raw_permalink if raw_permalink.startswith("http") else f"https://www.reddit.com{raw_permalink}"

        # Preserve complete stories that naturally fit within YouTube Shorts
        if 90 <= word_count <= 550:
            story_content = text
            word_cnt = word_count
        elif word_count > 550:
            story_content, word_cnt = trim_story_to_short(text, min_words=200, max_words=550)
        else:
            story_content = text
            word_cnt = word_count

        # Add viral engagement CTA question
        story_content = append_engagement_cta(story_content)
        word_cnt = len(story_content.split())

        story = {
            "title": gemini_title,
            "text": story_content,
            "part": 1,
            "total_parts": 1,
            "format": "short",
            "subreddit": subreddit
        }

        story_path = os.path.join(out_dir_today, f"story_{idx_today}.json")
        with open(story_path, "w", encoding="utf-8") as f:
            json.dump(story, f, indent=4, ensure_ascii=False)

        screenshot_path = os.path.join(out_dir_today, f"thumb_{idx_today}.png")
        try:
            get_or_create_thumbnail(post_url, gemini_title, story_content, screenshot_path, subreddit=subreddit, format="short")
        except Exception as thumb_err:
            print(f"⚠️ Thumbnail generation warning for story {idx_today}: {thumb_err}")

        # Record in persistent history database
        record_used_post(post, date_str_today, gemini_title, used_db)
        print(f"🎯 Saved fresh story_{idx_today}.json ({word_cnt} words, r/{subreddit}): {story_path}")
        shorts_collected += 1

    print(f"✅ Saved {shorts_collected} fresh stories for {date_str_today}")
    return date_str_today, shorts_collected

if __name__ == "__main__":
    target_d = None
    rep_idx = None
    for arg in sys.argv[1:]:
        if arg.isdigit() and len(arg) == 8:
            target_d = arg
        elif arg.startswith("--story="):
            rep_idx = int(arg.split("=")[1])
        elif arg.isdigit() and len(arg) == 1:
            rep_idx = int(arg)
    fetch_reddit_posts(target_date=target_d, replace_story_idx=rep_idx)
