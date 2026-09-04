import os
import sys
import glob
import random
import re
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_random_gameplay_clip():
    """
    Returns the path to a random gameplay clip from assets/gameplays.
    """
    gameplays_dir = os.path.join(PROJECT_ROOT, "assets", "gameplays")
    clips = glob.glob(os.path.join(gameplays_dir, "*.mp4")) + glob.glob(os.path.join(gameplays_dir, "*.mkv"))
    if clips:
        return random.choice(clips)
    return None


def extract_gameplay_frame(gameplay_path=None, width=1080, height=1920):
    """
    Extracts a high-definition random frame from a gameplay video.
    Returns a PIL RGBA Image.
    """
    if not gameplay_path or not os.path.exists(gameplay_path):
        gameplay_path = get_random_gameplay_clip()

    if gameplay_path and os.path.exists(gameplay_path):
        try:
            # Probe video duration
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                gameplay_path
            ]
            res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True)
            duration = float(res.stdout.strip()) if res.stdout.strip() else 60.0
            
            # Pick a random second
            start_sec = random.uniform(5.0, max(6.0, duration - 10.0))
            tmp_frame_path = os.path.join(PROJECT_ROOT, f"scratch_frame_{random.randint(1000, 9999)}.png")
            
            vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
            extract_cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-i", gameplay_path,
                "-vframes", "1",
                "-vf", vf,
                tmp_frame_path
            ]
            subprocess.run(extract_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            if os.path.exists(tmp_frame_path):
                img = Image.open(tmp_frame_path).convert("RGBA")
                try:
                    os.remove(tmp_frame_path)
                except Exception:
                    pass
                return img
        except Exception as e:
            print(f"⚠️ Could not extract video snippet frame: {e}")

    # Fallback to a sleek gradient dark canvas if no video exists
    return Image.new("RGBA", (width, height), (20, 22, 25, 255))


def get_system_font(bold=False, size=36):
    """
    Finds and loads a crisp system font (Arial, DejaVu, Liberation, etc.).
    """
    font_names = (
        ["arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf", "impact.ttf"]
        if bold else
        ["arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf", "FreeSans.ttf", "calibri.ttf"]
    )
    
    # Common font directories
    font_dirs = [
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/freefont",
        "/usr/share/fonts"
    ]
    
    for fname in font_names:
        for fdir in font_dirs:
            p = os.path.join(fdir, fname)
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        # Try direct load by name
        try:
            return ImageFont.truetype(fname, size)
        except Exception:
            pass

    return ImageFont.load_default()


def render_reddit_card_pil(title_text, subreddit, body_text="", card_width=920):
    """
    Renders a realistic, modern Reddit UI post card with rounded corners,
    subreddit logo, title, and upvote capsule.
    """
    pad = 36
    
    title_font = get_system_font(bold=True, size=44)
    body_font = get_system_font(bold=False, size=30)
    meta_font = get_system_font(bold=True, size=28)
    small_font = get_system_font(bold=False, size=24)

    # Clean title (strip [subreddit] tags so it matches real Reddit UI)
    title_text = re.sub(r"^\[.*?\]\s*", "", title_text).strip()

    # Clean body snippet (remove URLs and 'Original post:' links)
    if body_text:
        body_text = re.sub(r"https?://\S+", "", body_text)
        body_text = re.sub(r"Original post:\s*", "", body_text, flags=re.IGNORECASE)
        body_text = re.sub(r"\s+", " ", body_text).strip()

    # Inner usable width
    usable_w = card_width - (pad * 2)

    # Dynamic word wrapping based on pixel width
    words = title_text.split()
    wrapped_title = []
    current_line = []

    # Temporary draw object for measuring
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    for w in words:
        test_line = " ".join(current_line + [w])
        try:
            line_w = temp_draw.textlength(test_line, font=title_font)
        except Exception:
            line_w = len(test_line) * 26
        
        if line_w <= usable_w or not current_line:
            current_line.append(w)
        else:
            wrapped_title.append(current_line)
            current_line = [w]
    if current_line:
        wrapped_title.append(current_line)

    title_height = len(wrapped_title) * 56

    # Body snippet preview (wrapped cleanly)
    wrapped_body = []
    if body_text:
        b_words = body_text.split()
        b_curr = []
        for w in b_words:
            test_line = " ".join(b_curr + [w])
            try:
                line_w = temp_draw.textlength(test_line, font=body_font)
            except Exception:
                line_w = len(test_line) * 18
            if line_w <= usable_w or not b_curr:
                b_curr.append(w)
            else:
                wrapped_body.append(b_curr)
                b_curr = [w]
                if len(wrapped_body) >= 2:
                    break
        if b_curr and len(wrapped_body) < 2:
            wrapped_body.append(b_curr)

    body_height = (len(wrapped_body) * 38) if wrapped_body else 0
    card_height = pad + 40 + 16 + title_height + (16 + body_height if body_height else 0) + 24 + 48 + pad

    # Create transparent card surface
    card = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Card background (Reddit Dark Mode #181A1B) with border
    card_bg = (24, 26, 28, 245)
    draw.rounded_rectangle(
        [0, 0, card_width, card_height],
        radius=24,
        fill=card_bg,
        outline=(58, 62, 66, 255),
        width=2
    )

    # Subreddit icon (Reddit Orange circle with 'r/')
    icon_r = 18
    draw.ellipse([pad, pad, pad + icon_r * 2, pad + icon_r * 2], fill=(255, 69, 0, 255))
    draw.text((pad + 7, pad + 4), "r/", font=meta_font, fill=(255, 255, 255, 255))

    sub_label = f"r/{subreddit}"
    draw.text((pad + icon_r * 2 + 14, pad + 2), sub_label, font=meta_font, fill=(255, 255, 255, 255))

    try:
        sub_len = draw.textlength(sub_label, font=meta_font)
    except Exception:
        sub_len = len(sub_label) * 16
    draw.text((pad + icon_r * 2 + 14 + sub_len + 10, pad + 5), "• 4h ago", font=small_font, fill=(145, 150, 155, 255))

    # Justified Title Rendering (occupies full container width)
    curr_y = pad + icon_r * 2 + 18
    for idx, line_words in enumerate(wrapped_title):
        is_last_line = (idx == len(wrapped_title) - 1)
        if is_last_line or len(line_words) <= 1:
            draw.text((pad, curr_y), " ".join(line_words), font=title_font, fill=(245, 245, 248, 255))
        else:
            try:
                words_tot_w = sum(draw.textlength(w, font=title_font) for w in line_words)
                space_avail = usable_w - words_tot_w
                gap = space_avail / (len(line_words) - 1)
            except Exception:
                gap = 14
            
            # If gap is within reasonable justified range (not excessively stretched)
            if 6 <= gap <= 36:
                curr_x = pad
                for w in line_words:
                    draw.text((curr_x, curr_y), w, font=title_font, fill=(245, 245, 248, 255))
                    try:
                        w_len = draw.textlength(w, font=title_font)
                    except Exception:
                        w_len = len(w) * 26
                    curr_x += w_len + gap
            else:
                draw.text((pad, curr_y), " ".join(line_words), font=title_font, fill=(245, 245, 248, 255))
        curr_y += 56

    # Body snippet (cleanly styled)
    if wrapped_body:
        curr_y += 8
        for line_words in wrapped_body:
            draw.text((pad, curr_y), " ".join(line_words), font=body_font, fill=(180, 185, 190, 255))
            curr_y += 38

    # Upvotes Pill Badge
    curr_y += 18
    pill_w, pill_h = 160, 46
    draw.rounded_rectangle([pad, curr_y, pad + pill_w, curr_y + pill_h], radius=23, fill=(45, 48, 52, 255))
    draw.text((pad + 20, curr_y + 10), "▲ 24.8k ▼", font=small_font, fill=(220, 225, 230, 255))

    # Comments Pill
    c_x = pad + pill_w + 14
    c_w = 175
    draw.rounded_rectangle([c_x, curr_y, c_x + c_w, curr_y + pill_h], radius=23, fill=(45, 48, 52, 255))
    draw.text((c_x + 16, curr_y + 10), "💬 1.4k comments", font=small_font, fill=(175, 180, 185, 255))

    return card


def composite_card_over_background(card_img, bg_img, output_path, format="short"):
    """
    Overlays the Reddit Card with a Gaussian drop-shadow onto the background gameplay frame.
    """
    w, h = bg_img.size
    card_w, card_h = card_img.size

    # 1. Create soft drop shadow
    shadow_margin = 30
    shadow = Image.new("RGBA", (card_w + shadow_margin * 2, card_h + shadow_margin * 2), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [shadow_margin, shadow_margin, card_w + shadow_margin, card_h + shadow_margin],
        radius=24,
        fill=(0, 0, 0, 190)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))

    # 2. Position card (not full viewport, centered horizontally, upper-third)
    card_x = (w - card_w) // 2
    card_y = int(h * 0.22) if format == "short" else int(h * 0.16)

    # 3. Composite onto gameplay frame
    bg_img.paste(shadow, (card_x - shadow_margin, card_y - shadow_margin + 6), shadow)
    bg_img.paste(card_img, (card_x, card_y), card_img)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    bg_img.convert("RGB").save(output_path, "PNG")
    print(f"✅ Composite thumbnail saved: {output_path}")
    return output_path


def capture_reddit_screenshot_card(reddit_url, temp_save_path):
    """
    Attempts to capture only the Reddit post card element via Playwright.
    Returns the PIL Image if successful, None otherwise.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1080, "height": 1920}
            )
            page = context.new_page()
            page.goto(reddit_url, timeout=30000)

            # Accept cookies
            try:
                page.locator("text=Accept All").click(timeout=2000)
            except Exception:
                pass

            title_selector = "h1[id^='post-title-t3_']"
            body_selector = "div[id$='-post-rtjson-content']"

            title = page.wait_for_selector(title_selector, timeout=10000)
            content = page.wait_for_selector(body_selector, timeout=10000)

            title_box = title.bounding_box()
            content_box = content.bounding_box()

            if title_box and content_box:
                x = min(title_box["x"], content_box["x"]) - 16
                y = min(title_box["y"], content_box["y"]) - 16
                max_x = max(title_box["x"] + title_box["width"], content_box["x"] + content_box["width"]) + 16
                max_y = max(title_box["y"] + title_box["height"], content_box["y"] + content_box["height"]) + 16

                x = max(0, x)
                y = max(0, y)
                width = max_x - x
                height = min(max_y - y, 900)  # Cap height so it doesn't cover screen

                page.screenshot(path=temp_save_path, clip={"x": x, "y": y, "width": width, "height": height})
                browser.close()
                if os.path.exists(temp_save_path):
                    return Image.open(temp_save_path).convert("RGBA")
            browser.close()
    except Exception as e:
        print(f"ℹ️ Playwright card capture skipped ({e})")
    return None


def create_transparent_card_overlay(card_img, canvas_w=1080, canvas_h=1920, format="short"):
    """
    Places the Reddit Card with soft Gaussian drop-shadow onto an empty transparent canvas (1080x1920).
    This transparent image is overlaid onto the LIVE moving gameplay video in FFmpeg!
    """
    card_w, card_h = card_img.size
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Soft drop shadow
    shadow_margin = 30
    shadow = Image.new("RGBA", (card_w + shadow_margin * 2, card_h + shadow_margin * 2), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [shadow_margin, shadow_margin, card_w + shadow_margin, card_h + shadow_margin],
        radius=24,
        fill=(0, 0, 0, 190)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))

    card_x = (canvas_w - card_w) // 2
    card_y = int(canvas_h * 0.22) if format == "short" else int(canvas_h * 0.16)

    canvas.paste(shadow, (card_x - shadow_margin, card_y - shadow_margin + 6), shadow)
    canvas.paste(card_img, (card_x, card_y), card_img)
    return canvas


def create_reddit_thumbnail(title_text, subreddit="relationship_advice", body_text="", output_path="thumb.png", format="short", gameplay_path=None, post_url=None):
    """
    Master thumbnail generator:
    1. Extracts a random snippet frame from the selected gameplay video as the background for the YouTube thumbnail image.
    2. Overlays the Reddit post card (either Playwright screenshot or realistic Reddit UI card)
       in the foreground.
    3. Saves both:
       - thumb_{idx}.png (Full composite for YouTube thumbnail upload)
       - card_{idx}.png (1080x1920 transparent card for live moving gameplay video intro overlay)
    """
    w, h = (1080, 1920) if format == "short" else (1920, 1080)
    card_w = int(w * 0.86)

    # 1. Background gameplay video snippet frame (for YouTube thumbnail)
    bg_img = extract_gameplay_frame(gameplay_path=gameplay_path, width=w, height=h)

    # 2. Foreground Reddit Card
    card_img = None
    if post_url:
        temp_cap = os.path.join(PROJECT_ROOT, f"temp_cap_{random.randint(1000, 9999)}.png")
        card_img = capture_reddit_screenshot_card(post_url, temp_cap)
        if os.path.exists(temp_cap):
            try:
                os.remove(temp_cap)
            except Exception:
                pass
        if card_img:
            # Resize captured card to fit width
            aspect = card_img.height / card_img.width
            new_h = int(card_w * aspect)
            new_h = min(new_h, int(h * 0.45)) # Cap height
            card_img = card_img.resize((card_w, new_h), Image.Resampling.LANCZOS)

    # If no screenshot captured, render the realistic Reddit Card
    if card_img is None:
        card_img = render_reddit_card_pil(title_text, subreddit, body_text=body_text, card_width=card_w)

    # 3. Save transparent card overlay (used over live video gameplay during title intro)
    card_overlay_path = output_path.replace("thumb_", "card_")
    if card_overlay_path != output_path:
        card_canvas = create_transparent_card_overlay(card_img, canvas_w=w, canvas_h=h, format=format)
        os.makedirs(os.path.dirname(os.path.abspath(card_overlay_path)), exist_ok=True)
        card_canvas.save(card_overlay_path, "PNG")
        print(f"✅ Transparent card overlay saved: {card_overlay_path}")

    # 4. Composite card in foreground over static gameplay background (for YouTube thumbnail)
    return composite_card_over_background(card_img, bg_img, output_path, format=format)


# Backwards compatibility wrappers
def capture_reddit_screenshot(reddit_url, save_path, retries=1, delay=1):
    return False

def create_fallback_thumbnail(title_text, body_text, output_path, width=1080, height=1920):
    return create_reddit_thumbnail(title_text, "relationship_advice", body_text, output_path)
