import random
import google.generativeai as genai
import os
import sys
import re
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

HOOKS = ["INSANE", "KARMA", "REVENGE", "EXPOSED", "UNBELIEVABLE", "HEARTBREAKING", "SHOCKING", "TWISTED"]

def local_title_enhancer(title):
    if any(h.lower() in title.lower() for h in HOOKS):
        return title
    return f"{title} | {random.choice(HOOKS)}"

def clean_title_for_ffmpeg(title):
    title = title.split('\n')[0]  # take only the first line
    title = re.sub(r'[^\x00-\x7F]+', '', title)  # remove non-ASCII chars (like emojis)
    title = re.sub(r'[\'":]', '', title)  # remove quotes and colons
    return title.strip()

def generate_title_with_gemini(text, fallback_title):
    try:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return fallback_title
        genai.configure(api_key=api_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        model = genai.GenerativeModel(model_name=model_name)

        # Extract subreddit prefix (e.g., "[AskReddit]") from the fallback_title
        match = re.match(r"^\[(.*?)\]\s*(.*)", fallback_title)
        subreddit = match.group(1) if match else "Reddit"
        original_title = match.group(2) if match else fallback_title

        prompt = (
            f"You're creating a YouTube title for a viral story from r/{subreddit}.\n"
            "Make it under 60 characters, catchy and clickable.\n"
            "No emojis, lists, or suggestions. Respond with just the title:\n\n"
            f"Original Reddit title: {original_title}\n"
            f"Story snippet: {text[:800]}\n"
        )

        response = model.generate_content(prompt)
        gemini_title = response.candidates[0].content.parts[0].text.strip()
        cleaned = clean_title_for_ffmpeg(gemini_title)

        # Re-append the subreddit prefix
        return f"[{subreddit}] {cleaned or original_title}"
    except Exception as e:
        print(f"⚠️ Gemini failed, fallback title used: {e}")
        return fallback_title
