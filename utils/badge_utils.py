import os
import sys
from PIL import Image, ImageDraw, ImageFont

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def create_breakdown_badge(out_path=None, text="THE BREAKDOWN", width=1080, height=1920):
    """
    Generates a stunning, modern gradient pill badge for 'THE BREAKDOWN' segment
    as a transparent 1080x1920 PNG overlay.
    """
    if out_path is None:
        out_path = os.path.join(PROJECT_ROOT, "assets", "breakdown_badge.png")
    
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Pill dimensions
    badge_w = 480
    badge_h = 76
    badge_x = (width - badge_w) // 2
    badge_y = 190
    corner_r = badge_h // 2

    # Draw soft outer glow / drop shadow
    for offset in range(8, 0, -2):
        alpha = int(40 - offset * 4)
        draw.rounded_rectangle(
            [badge_x - offset, badge_y - offset + 4, badge_x + badge_w + offset, badge_y + badge_h + offset + 4],
            radius=corner_r + offset,
            fill=(0, 0, 0, alpha)
        )

    # Draw vibrant gradient pill (Left: #FF1361 to Right: #FFF800 or #7F00FF to #FF007F)
    pill = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    pill_draw = ImageDraw.Draw(pill)

    for x in range(badge_w):
        factor = x / float(badge_w)
        r = int(255 * (1 - factor) + 255 * factor)
        g = int(30 * (1 - factor) + 140 * factor)
        b = int(90 * (1 - factor) + 0 * factor)
        pill_draw.line([(x, 0), (x, badge_h)], fill=(r, g, b, 245))

    # Mask with rounded rectangle
    mask = Image.new("L", (badge_w, badge_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, badge_w, badge_h], radius=corner_r, fill=255)

    img.paste(pill, (badge_x, badge_y), mask)

    # Draw crisp outer highlight border
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=corner_r,
        outline=(255, 255, 255, 230),
        width=3
    )

    # Load bold font
    font = None
    for font_path in [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "assets/fonts/Impact.ttf"
    ]:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, 34)
                break
            except Exception:
                pass
    if not font:
        font = ImageFont.load_default()

    # Draw badge title
    display_text = f"THE BREAKDOWN"
    bbox = draw.textbbox((0, 0), display_text, font=font)
    t_w = bbox[2] - bbox[0]
    t_h = bbox[3] - bbox[1]

    t_x = badge_x + (badge_w - t_w) // 2
    t_y = badge_y + (badge_h - t_h) // 2 - 2

    # Text shadow
    draw.text((t_x + 2, t_y + 2), display_text, font=font, fill=(0, 0, 0, 200))
    # Text body
    draw.text((t_x, t_y), display_text, font=font, fill=(255, 255, 255, 255))

    img.save(out_path, "PNG")
    print(f"✅ Generated breakdown badge at: {out_path}")
    return out_path

if __name__ == "__main__":
    create_breakdown_badge()
