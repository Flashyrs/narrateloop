import os
import time
import subprocess
import textwrap
from shlex import quote
from playwright.sync_api import sync_playwright


def capture_reddit_screenshot(reddit_url, save_path, retries=3, delay=2):
    """
    Attempts to capture a clean screenshot of a Reddit post using Playwright.
    If it fails after all retries, falls back to full-page capture or returns False.
    """
    for attempt in range(1, retries + 1):
        try:
            print(f"🔁 Attempt {attempt} to capture screenshot...")
            return _capture_with_playwright(reddit_url, save_path)
        except Exception as e:
            print(f"⚠️ Screenshot attempt {attempt} failed: {e}")
            time.sleep(delay)

    # If all attempts fail, try a full-page fallback capture
    fallback_path = os.path.splitext(save_path)[0] + "_full.png"
    try:
        print("📄 Trying full-page fallback...")
        return _capture_with_playwright(reddit_url, fallback_path, full_page=True)
    except Exception as fallback_e:
        print(f"❌ Final fallback failed: {fallback_e}")
        return False


def _capture_with_playwright(reddit_url, save_path, full_page=False):
    """
    Handles Playwright page launch, navigation, and screenshot capture logic.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            locale="en-US",
            viewport={"width": 1080, "height": 1920},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1"
            }
        )

        page = context.new_page()
        print(f"🌐 Opening Reddit post: {reddit_url}")
        page.goto(reddit_url, timeout=90000)

        # Handle cookie consent
        try:
            page.locator("text=Accept All").click(timeout=3000)
            page.wait_for_timeout(1000)
        except:
            pass  # Ignore if not shown

        # Optional scroll to help load post content
        for _ in range(3):
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(600)

        # Try expanding long posts
        try:
            read_more = page.locator("text=Read more")
            if read_more.is_visible():
                read_more.click(timeout=2000)
                page.wait_for_timeout(1000)
        except:
            pass  # Not all posts have 'Read more'

        # Required elements to screenshot
        title_selector = "h1[id^='post-title-t3_']"
        body_selector = "div[id$='-post-rtjson-content']"

        try:
            title = page.wait_for_selector(title_selector, timeout=30000)
            content = page.wait_for_selector(body_selector, timeout=30000)
        except Exception as e:
            raise Exception(f"❌ Could not locate title or content area: {e}")

        # Scroll both elements into view
        page.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})", title)
        page.wait_for_timeout(500)
        page.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})", content)
        page.wait_for_timeout(500)

        if full_page:
            page.screenshot(path=save_path, full_page=True)
            print(f"📸 Full-page fallback screenshot saved: {save_path}")
            return True

        # Calculate bounding box for precise crop
        title_box = title.bounding_box()
        content_box = content.bounding_box()

        if title_box and content_box:
            x = min(title_box["x"], content_box["x"])
            y = min(title_box["y"], content_box["y"])
            max_x = max(title_box["x"] + title_box["width"], content_box["x"] + content_box["width"])
            max_y = max(title_box["y"] + title_box["height"], content_box["y"] + content_box["height"])

            width = max_x - x
            height = max_y - y

            # Avoid overflow beyond viewport
            viewport = page.viewport_size
            width = min(width, viewport["width"] - x)
            height = min(height, viewport["height"] - y)

            if width > 0 and height > 0:
                page.screenshot(path=save_path, clip={
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                })
                print(f"✅ Screenshot saved: {save_path}")
                return True

        raise Exception("❌ Invalid bounding box or empty clip area.")


# ------------------ TEXT CLEANING HELPERS ------------------ #

def clean_text(text):
    """
    Removes problematic characters and normalizes ASCII.
    """
    return (
        text.encode("ascii", errors="ignore").decode()
        .replace(":", "")
        .replace("'", "")
        .replace("\"", "")
        .strip()
    )


def escape_ffmpeg_text(text):
    """
    Escapes text for safe FFmpeg usage in drawtext filters.
    """
    return text.replace("'", r"\'").replace(":", r"\:")


# ------------------ FALLBACK IMAGE GENERATOR ------------------ #

def create_fallback_thumbnail(title_text, body_text, output_path, width=1080, height=1920):
    """
    Uses FFmpeg to create a basic image with title and body text if Playwright fails.
    """
    print("🛠️ Creating fallback thumbnail using FFmpeg...")

    # Wrap and sanitize text
    title_wrapped = '\\n'.join(textwrap.wrap(clean_text(title_text), width=30))
    body_wrapped = '\\n'.join(textwrap.wrap(clean_text(body_text), width=50))

    # Escape for drawtext filter
    safe_title = escape_ffmpeg_text(title_wrapped)
    safe_body = escape_ffmpeg_text(body_wrapped)

    # Font paths (customize if needed)
    Copper = r"C:\Windows\Fonts\Copperplate Gothic.ttf"
    Tw = r"C:\Windows\Fonts\Tw Cen MT.ttf"

    # Build FFmpeg filter text
    filter_text = (
        f"color=white@1.0:s={width}x{height},"
        f"drawbox=color=orange@1.0:x=0:y=0:w=iw:h=ih:t=40,"
        f"drawtext=fontfile='{Copper}':text='{safe_title}':"
        f"fontcolor=black:fontsize=64:x=(w-text_w)/2:y=100:"
        f"box=1:boxcolor=white@0.85:boxborderw=30:line_spacing=10,"
        f"drawtext=fontfile='{Tw}':text='{safe_body}':"
        f"fontcolor=black:fontsize=42:x=100:y=400:"
        f"box=1:boxcolor=white@0.75:boxborderw=20:line_spacing=8"
    )

    cmd = [
        "ffmpeg", "-f", "lavfi", "-i", filter_text,
        "-frames:v", "1", "-y", output_path
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Fallback thumbnail created: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg fallback error: {e}")
