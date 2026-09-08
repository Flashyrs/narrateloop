import os
import re
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_font(size, bold=False):
    font_paths = [
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\Montserrat-Bold.ttf" if bold else "C:\\Windows\\Fonts\\Montserrat-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def create_paged_chat_card(page_messages, contact_name="Messages", output_path=None, width=1080, height=1920, full_page_messages=None):
    """
    Renders an authentic, pure-white iOS iMessage Conversation Card.
    Supports fixed page container frame with progressive step-by-step message appearance.
    """
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "scratch", "test_chat.png")

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if not page_messages:
        img.save(output_path, "PNG")
        return output_path

    card_w = 940
    card_x = (width - card_w) // 2
    card_y = 190

    font_name = _get_font(28, bold=True)
    font_sub = _get_font(18, bold=False)
    font_avatar = _get_font(34, bold=True)
    font_msg = _get_font(28, bold=False)

    pad_h = 24
    pad_v = 18
    line_h = 36
    bubble_spacing = 16
    max_bubble_w = 640

    def parse_msg_bubble(msg):
        sender = msg.get("sender", "Them").strip()
        text = msg.get("text", "").strip()
        is_me = msg.get("is_me", False) or sender.lower() in ["me", "op", "self", "i"]

        words = text.split()
        lines = []
        cur_line = []
        for w in words:
            test_line = " ".join(cur_line + [w])
            bbox = draw.textbbox((0, 0), test_line, font=font_msg)
            if (bbox[2] - bbox[0]) <= (max_bubble_w - pad_h * 2):
                cur_line.append(w)
            else:
                if cur_line:
                    lines.append(" ".join(cur_line))
                cur_line = [w]
        if cur_line:
            lines.append(" ".join(cur_line))

        max_lw = 0
        for l in lines:
            bbox = draw.textbbox((0, 0), l, font=font_msg)
            lw = bbox[2] - bbox[0]
            if lw > max_lw:
                max_lw = lw

        bw = max(140, max_lw + pad_h * 2)
        bh = len(lines) * line_h + pad_v * 2
        return {
            "is_me": is_me,
            "sender": sender,
            "lines": lines,
            "width": bw,
            "height": bh
        }

    # Use full page messages for calculating stable container height if provided
    layout_ref_msgs = full_page_messages[:3] if full_page_messages else page_messages[:3]
    total_messages_h = 0
    for m in layout_ref_msgs:
        b_info = parse_msg_bubble(m)
        total_messages_h += b_info["height"] + bubble_spacing

    # Parse actual visible messages for this step
    bubbles_data = [parse_msg_bubble(m) for m in page_messages[:3]]

    header_h = 130
    card_h = header_h + total_messages_h + 25

    # 1. Soft Drop Shadow
    for offset in range(16, 0, -2):
        alpha = int(45 * (1 - offset / 16))
        draw.rounded_rectangle(
            [card_x - offset, card_y - offset + 8, card_x + card_w + offset, card_y + card_h + offset + 8],
            radius=40,
            fill=(0, 0, 0, alpha)
        )

    # 2. Main White Container Card (#FFFFFF)
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=36,
        fill=(255, 255, 255, 252),
        outline=(218, 222, 230, 255),
        width=3
    )

    # 3. Top-Center Header Section
    header_contact = contact_name if contact_name else "Messages"
    header_cx = card_x + card_w // 2

    # Centered Avatar Circle
    avatar_r = 28
    avatar_cy = card_y + 40
    draw.ellipse(
        [header_cx - avatar_r, avatar_cy - avatar_r, header_cx + avatar_r, avatar_cy + avatar_r],
        fill=(142, 142, 147, 255)
    )
    initial = header_contact[0].upper() if header_contact else "M"
    abbox = draw.textbbox((0, 0), initial, font=font_avatar)
    aw = abbox[2] - abbox[0]
    ah = abbox[3] - abbox[1]
    draw.text((header_cx - aw // 2, avatar_cy - ah // 2 - 2), initial, font=font_avatar, fill=(255, 255, 255, 255))

    # Centered Contact Name
    nbbox = draw.textbbox((0, 0), header_contact, font=font_name)
    nw = nbbox[2] - nbbox[0]
    draw.text((header_cx - nw // 2, card_y + 75), header_contact, font=font_name, fill=(0, 0, 0, 255))

    # Centered "iMessage" Subtitle
    sbbox = draw.textbbox((0, 0), "iMessage", font=font_sub)
    sw = sbbox[2] - sbbox[0]
    draw.text((header_cx - sw // 2, card_y + 104), "iMessage", font=font_sub, fill=(142, 142, 147, 255))

    # Header Separator Line
    draw.line(
        [(card_x + 20, card_y + header_h), (card_x + card_w - 20, card_y + header_h)],
        fill=(230, 232, 238, 255),
        width=2
    )

    # 4. Render Message Bubbles
    curr_y = card_y + header_h + 18
    for b in bubbles_data:
        bw = b["width"]
        bh = b["height"]
        is_me = b["is_me"]
        lines = b["lines"]

        if is_me:
            # SENDER (RIGHT): iOS Blue #007AFF
            bx = card_x + card_w - bw - 35
            bubble_fill = (0, 122, 255, 255)
            text_fill = (255, 255, 255, 255)
            draw.rounded_rectangle(
                [bx, curr_y, bx + bw, curr_y + bh],
                radius=22,
                fill=bubble_fill
            )
        else:
            # RECEIVER (LEFT): iOS Light Gray #E9E9EB
            bx = card_x + 35
            bubble_fill = (233, 233, 235, 255)
            text_fill = (0, 0, 0, 245)
            draw.rounded_rectangle(
                [bx, curr_y, bx + bw, curr_y + bh],
                radius=22,
                fill=bubble_fill
            )

        text_y = curr_y + pad_v - 2
        for line in lines:
            draw.text((bx + pad_h, text_y), line, font=font_msg, fill=text_fill)
            text_y += line_h

        curr_y += bh + bubble_spacing

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def generate_paged_chat_step_cards(all_messages, contact_name="Messages", output_dir=None, story_name=1):
    """
    Generates step-by-step animation frames for conversation shorts:
    - Groups messages into pages of 3.
    - At each step within a page, a new message appears.
    - When transitioning to a new page, the screen clears.
    """
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "scratch")
    os.makedirs(output_dir, exist_ok=True)

    step_entries = []
    num_msgs = len(all_messages)
    for p_idx in range(0, num_msgs, 3):
        page_slice = all_messages[p_idx:p_idx+3]
        for sub_i in range(len(page_slice)):
            global_idx = p_idx + sub_i
            visible_slice = page_slice[:sub_i+1]
            out_file = os.path.join(output_dir, f"chat_{story_name}_step_{global_idx}.png")
            create_paged_chat_card(visible_slice, contact_name=contact_name, output_path=out_file, full_page_messages=page_slice)
            step_entries.append((global_idx, out_file, p_idx // 3))
    return step_entries

# Alias for backwards compatibility
create_chat_bubble_card = create_paged_chat_card


def create_quote_callout_card(quote_text, speaker="THE STORY", output_path=None, width=1080, height=1920):
    """
    Renders an elegant, 100% consistent quote card with:
    1. Large Quotation Mark ('“') pinned on the left
    2. Quote text cleanly justified between the quotation mark and right margin
    3. Speaker attribution ('— WHO SAID IT') right-aligned inside the border with guaranteed zero overflow
    """
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "scratch", "test_quote.png")

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if not quote_text:
        img.save(output_path, "PNG")
        return output_path

    card_w = 940
    card_x = (width - card_w) // 2
    card_y = 220

    clean_q = quote_text.strip().replace('"', '').replace('“', '').replace('”', '').replace("'", "")
    
    # Auto-scale font based on length
    if len(clean_q) > 130:
        font_size = 28
        line_h = 40
        max_line_pixels = 720
    elif len(clean_q) > 80:
        font_size = 32
        line_h = 44
        max_line_pixels = 730
    else:
        font_size = 36
        line_h = 50
        max_line_pixels = 730

    font_pill = _get_font(22, bold=True)
    font_quote = _get_font(font_size, bold=True)
    font_speaker = _get_font(26, bold=True)
    font_mark = _get_font(96, bold=True)

    # Word wrapping with strict bounding box inside the text area
    words = clean_q.split()
    lines = []
    cur_line = []
    for w in words:
        test_line = " ".join(cur_line + [w])
        bbox = draw.textbbox((0, 0), test_line, font=font_quote)
        if (bbox[2] - bbox[0]) <= max_line_pixels:
            cur_line.append(w)
        else:
            if cur_line:
                lines.append(" ".join(cur_line))
            cur_line = [w]
    if cur_line:
        lines.append(" ".join(cur_line))

    # Calculate total height
    content_h = len(lines) * line_h
    card_h = 135 + max(content_h, 80) + 70

    # 1. Outer drop shadow
    for offset in range(14, 0, -2):
        alpha = int(40 * (1 - offset / 14))
        draw.rounded_rectangle(
            [card_x - offset, card_y - offset + 8, card_x + card_w + offset, card_y + card_h + offset + 8],
            radius=38,
            fill=(0, 0, 0, alpha)
        )

    # 2. Main Card background (Deep Obsidian Navy #10131C)
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=32,
        fill=(16, 20, 30, 250),
        outline=(255, 170, 0, 230), # Radiant amber-gold border
        width=3
    )

    # 3. Top Tag Pill
    pill_text = "KEY STATEMENT"
    pill_w = 220
    pill_h = 40
    pill_x = card_x + 45
    pill_y = card_y + 28
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=20,
        fill=(255, 69, 0, 255) # Crimson
    )
    pbbox = draw.textbbox((0, 0), pill_text, font=font_pill)
    pw = pbbox[2] - pbbox[0]
    draw.text((pill_x + (pill_w - pw) // 2, pill_y + 8), pill_text, font=font_pill, fill=(255, 255, 255, 255))

    # 4. Large Quotation Mark pinned on Left Column
    draw.text((card_x + 42, card_y + 80), "“", font=font_mark, fill=(255, 170, 0, 220))

    # 5. Quote Text Block (Column between Quote Mark and Right Margin)
    text_start_x = card_x + 130
    text_y = card_y + 105
    for l in lines:
        draw.text((text_start_x, text_y), l, font=font_quote, fill=(255, 255, 255, 255))
        text_y += line_h

    # 6. Speaker Attribution Footer (Guaranteed Inside Right Margin)
    speaker_clean = speaker.strip().upper() if speaker else "THE STORY"
    spk_label = f"— {speaker_clean}"
    sbbox = draw.textbbox((0, 0), spk_label, font=font_speaker)
    sw = sbbox[2] - sbbox[0]

    # Auto-scale font if speaker string is exceptionally long
    if sw > (card_w - 140):
        font_speaker = _get_font(20, bold=True)
        sbbox = draw.textbbox((0, 0), spk_label, font=font_speaker)
        sw = sbbox[2] - sbbox[0]

    spk_x = card_x + card_w - sw - 50
    draw.text((spk_x, text_y + 18), spk_label, font=font_speaker, fill=(255, 215, 0, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def create_behavioral_analysis_card(red_flags, output_path=None, width=1080, height=1920):
    """
    Renders an in-depth Psychological & Behavioral Analysis Matrix card.
    """
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "scratch", "test_analysis_card.png")

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if not red_flags:
        img.save(output_path, "PNG")
        return output_path

    card_w = 940
    card_x = (width - card_w) // 2
    card_y = 280

    font_header = _get_font(30, bold=True)
    font_num = _get_font(24, bold=True)
    font_flag = _get_font(28, bold=True)

    items = red_flags[:3]
    item_h = 82
    item_spacing = 16
    card_h = 105 + len(items) * (item_h + item_spacing) + 20

    # Outer drop shadow
    for offset in range(14, 0, -2):
        alpha = int(35 * (1 - offset / 14))
        draw.rounded_rectangle(
            [card_x - offset, card_y - offset + 8, card_x + card_w + offset, card_y + card_h + offset + 8],
            radius=38,
            fill=(0, 0, 0, alpha)
        )

    # Main Card background
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=32,
        fill=(16, 20, 32, 245),
        outline=(255, 190, 0, 230),
        width=3
    )

    # Card Title
    draw.text((card_x + 40, card_y + 30), "KEY BEHAVIORAL PATTERNS", font=font_header, fill=(255, 215, 0, 255))
    
    # Separator line
    draw.line(
        [(card_x + 30, card_y + 80), (card_x + card_w - 30, card_y + 80)],
        fill=(55, 65, 88, 200),
        width=2
    )

    curr_y = card_y + 98
    for i, flag in enumerate(items):
        draw.rounded_rectangle(
            [card_x + 35, curr_y, card_x + card_w - 35, curr_y + item_h],
            radius=18,
            fill=(28, 35, 52, 230),
            outline=(255, 80, 80, 160) if i == 0 else (90, 120, 180, 140),
            width=2
        )

        badge_color = (255, 59, 48, 255) if i == 0 else (0, 122, 255, 255)
        draw.rounded_rectangle(
            [card_x + 52, curr_y + 16, card_x + 105, curr_y + item_h - 16],
            radius=12,
            fill=badge_color
        )
        num_text = f"0{i+1}"
        draw.text((card_x + 65, curr_y + 24), num_text, font=font_num, fill=(255, 255, 255, 255))

        flag_clean = flag.strip()
        if len(flag_clean) > 36:
            flag_clean = flag_clean[:34] + "..."
        draw.text((card_x + 125, curr_y + 24), flag_clean, font=font_flag, fill=(255, 255, 255, 255))

        curr_y += item_h + item_spacing

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def create_community_verdict_card(verdict_title="WHO IS WRONG?", opt_a="NOT THE JERK", pct_a=82, opt_b="AT FAULT", pct_b=18, takeaway="You do not owe anyone your peace.", output_path=None, width=1080, height=1920):
    """
    Renders the high-impact Community Verdict / Moral Split Card for Slot 3:
    - Glowing emerald/crimson comparison bars
    - Community takeaway quote pill
    """
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "scratch", "test_verdict_card.png")

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    card_w = 940
    card_x = (width - card_w) // 2
    card_y = 230

    font_pill = _get_font(22, bold=True)
    font_title = _get_font(32, bold=True)
    font_bar = _get_font(26, bold=True)
    font_takeaway = _get_font(24, bold=False)

    card_h = 440

    # 1. Outer drop shadow
    for offset in range(14, 0, -2):
        alpha = int(35 * (1 - offset / 14))
        draw.rounded_rectangle(
            [card_x - offset, card_y - offset + 8, card_x + card_w + offset, card_y + card_h + offset + 8],
            radius=38,
            fill=(0, 0, 0, alpha)
        )

    # 2. Main Card background
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=32,
        fill=(16, 20, 32, 248),
        outline=(50, 205, 50, 220), # Lime Emerald Border
        width=3
    )

    # 3. Top Tag Pill
    pill_text = "COMMUNITY VERDICT"
    pill_w = 260
    pill_h = 38
    pill_x = card_x + 40
    pill_y = card_y + 26
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=19,
        fill=(46, 139, 87, 255) # Sea Green
    )
    pbbox = draw.textbbox((0, 0), pill_text, font=font_pill)
    pw = pbbox[2] - pbbox[0]
    draw.text((pill_x + (pill_w - pw) // 2, pill_y + 7), pill_text, font=font_pill, fill=(255, 255, 255, 255))

    # 4. Verdict Title
    draw.text((card_x + 40, card_y + 76), verdict_title, font=font_title, fill=(255, 255, 255, 255))

    # 5. Option A Bar (Emerald)
    bar_x = card_x + 40
    bar_w = card_w - 80
    bar_y_a = card_y + 135
    bar_h = 58
    draw.rounded_rectangle([bar_x, bar_y_a, bar_x + bar_w, bar_y_a + bar_h], radius=16, fill=(35, 42, 58, 255))
    fill_w_a = int(bar_w * (pct_a / 100.0))
    draw.rounded_rectangle([bar_x, bar_y_a, bar_x + fill_w_a, bar_y_a + bar_h], radius=16, fill=(46, 204, 113, 255))
    draw.text((bar_x + 20, bar_y_a + 14), f"{pct_a}% {opt_a}", font=font_bar, fill=(255, 255, 255, 255))

    # 6. Option B Bar (Crimson)
    bar_y_b = bar_y_a + bar_h + 16
    draw.rounded_rectangle([bar_x, bar_y_b, bar_x + bar_w, bar_y_b + bar_h], radius=16, fill=(35, 42, 58, 255))
    fill_w_b = int(bar_w * (pct_b / 100.0))
    draw.rounded_rectangle([bar_x, bar_y_b, bar_x + fill_w_b, bar_y_b + bar_h], radius=16, fill=(231, 76, 60, 255))
    draw.text((bar_x + 20, bar_y_b + 14), f"{pct_b}% {opt_b}", font=font_bar, fill=(255, 255, 255, 255))

    # 7. Takeaway Footer
    footer_y = bar_y_b + bar_h + 24
    clean_tk = takeaway.strip().replace('"', '')
    if len(clean_tk) > 72:
        clean_tk = clean_tk[:69] + "..."
    draw.text((card_x + 40, footer_y), f"TAKEAWAY: “{clean_tk}”", font=font_takeaway, fill=(255, 215, 0, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path
