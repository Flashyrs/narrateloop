import os
import json
import random
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

EMPHASIZED_PHRASES = {
    "no more", "never again", "i'm done", "that's it", "not anymore",
    "i finally said", "enough is enough", "i had enough", "i told them", "i can't do this",
    "i give up", "i stood my ground", "i said no", "i chose myself", "i walked away",
    "i’m not a bank", "i put myself first", "this ends now", "they crossed the line"
}

def seconds_to_ass_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"

def clean_word(word):
    return word.strip().replace("\n", " ").replace("\xa0", " ")

def is_phrase_emphasized(word, full_text):
    word_lower = word.lower()
    return any(phrase for phrase in EMPHASIZED_PHRASES if word_lower in phrase and phrase in full_text.lower())

def generate_subs(date_str, story_name, format="short"):
    subtitle_dir = os.path.join(PROJECT_ROOT, "subtitles")
    os.makedirs(subtitle_dir, exist_ok=True)

    timing_path = os.path.join(PROJECT_ROOT, "audio", date_str, f"voice_{story_name}_timing.json")
    story_path = os.path.join(PROJECT_ROOT, "reddit_stories", date_str, f"story_{story_name}.json")
    subtitle_path = os.path.join(subtitle_dir, f"{date_str}_{story_name}_{format}.ass")

    with open(timing_path, "r", encoding="utf-8") as f:
        timing_data = json.load(f)

    if isinstance(timing_data, dict):
        title_end_time = float(timing_data.get("title_end_time", 0.0))
        word_timings = timing_data.get("words", [])
    else:
        title_end_time = 0.0
        word_timings = timing_data

    with open(story_path, "r", encoding="utf-8") as f:
        story_text = json.load(f).get("text", "")

    word_timings = sorted(word_timings, key=lambda w: w.get("start", 0))
    max_duration = 0.4
    safety_margin = 0.01

    if format == "short":
        play_x, play_y, font_size = 1080, 1920, 110
    else:
        play_x, play_y, font_size = 1920, 1080, 70

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, OutlineColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: BoldCenter, Impact, {font_size}, &H00FFFFFF, &H64000000, &H00000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 0, 5, 0, 0, 0, 1
Style: EmphasizedRed, Impact, {font_size}, &H000000FF, &H64000000, &H00000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 0, 5, 0, 0, 0, 1
Style: RhythmYellow, Impact, {font_size}, &H0000FFFF, &H64000000, &H00000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 0, 5, 0, 0, 0, 1


[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if format == "video":
        i = 0
        while i < len(word_timings):
            group = word_timings[i:i+3]
            if not group:
                break

            start = max(float(group[0]["start"]), 0.01)
            end = float(group[-1]["end"])

            # Skip subtitle groups that occur during title thumbnail display
            if start < title_end_time:
                i += 3
                continue

            start_str = seconds_to_ass_time(start)
            end_str = seconds_to_ass_time(end)

            # Randomly pick 1 word index to highlight yellow (unless it's emphasized)
            yellow_index = random.randint(0, len(group) - 1)

            styled_line = ""
            for j, word_data in enumerate(group):
                word = clean_word(word_data["word"])
                if is_phrase_emphasized(word, story_text):
                    styled_line += f"{{\\rEmphasizedRed}}{word} "
                elif j == yellow_index:
                    styled_line += f"{{\\rRhythmYellow}}{word} "
                else:
                    styled_line += f"{{\\rBoldCenter}}{word} "

            styled_line = styled_line.strip()
            ass_content += f"Dialogue: 0,{start_str},{end_str},BoldCenter,,0,0,0,,{styled_line}\n"
            i += 3

    else:  # format == "short"
        for i, word in enumerate(word_timings):
            try:
                start = float(word["start"])
                end = float(word["end"])
                text = clean_word(str(word["word"]))

                if not text or end <= 0 or start < 0:
                    continue

                # Skip words that occur during title card display
                if start < title_end_time:
                    continue

                if i + 1 < len(word_timings):
                    next_start = float(word_timings[i + 1].get("start", end))
                    end = min(end, next_start - safety_margin)

                end = max(start + 0.01, min(end, start + max_duration))

                start_str = seconds_to_ass_time(start)
                end_str = seconds_to_ass_time(end)

                if is_phrase_emphasized(text, story_text):
                    style = "EmphasizedRed"
                elif random.random() < 0.33:  # ~33% chance for yellow
                    style = "RhythmYellow"
                else:
                    style = "BoldCenter"

                ass_content += f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{text}\n"

            except Exception as e:
                print(f"[ERROR] Skipping word due to parsing error: {word} — {e}")
                continue

    with open(subtitle_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return subtitle_path
if __name__ == "__main__":
    date_str = datetime.now().strftime("%Y%m%d")
    for name in ["1", "2", "3"]:
        print("Shorts:", generate_subs(date_str, name, "short"))
        print("Video :", generate_subs(date_str, name, "video"))



# import os
# import json
# from datetime import datetime, timedelta

# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# def seconds_to_ass_time(seconds):
#     hours = int(seconds // 3600)
#     minutes = int((seconds % 3600) // 60)
#     secs = int(seconds % 60)
#     centis = int((seconds - int(seconds)) * 100)
#     return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"

# def clean_word(word):
#     return word.strip().replace("\n", " ").replace("\xa0", " ")

# def is_emphasized(word):
#     word_lower = word.lower()
#     return (
#         word.isupper() and len(word) > 1 or
#         "*" in word or "_" in word or
#         word_lower in {"important", "never", "always", "urgent", "seriously"}
#     )

# def generate_subs(date_str, story_name):
#     subtitle_dir = os.path.join(PROJECT_ROOT, "subtitles")
#     os.makedirs(subtitle_dir, exist_ok=True)

#     timing_path = os.path.join(PROJECT_ROOT, "audio", date_str, f"voice_{story_name}_timing.json")
#     subtitle_path = os.path.join(subtitle_dir, f"{date_str}_{story_name}.ass")

#     with open(timing_path, "r", encoding="utf-8") as f:
#         word_timings = json.load(f)

#     word_timings = sorted(word_timings, key=lambda w: w.get("start", 0))

#     max_duration = 0.4
#     safety_margin = 0.01

#     ass_content = """[Script Info]
# ScriptType: v4.00+
# PlayResX: 1080
# PlayResY: 1920

# [V4+ Styles]
# Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, OutlineColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
# Style: BoldCenter, Impact, 110, &H00FFFFFF, &H64000000, &H00000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 0, 5, 0, 0, 0, 1
# Style: Emphasized, Impact, 110, &H0000FFFF, &H64000000, &H00000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 0, 5, 0, 0, 0, 1

# [Events]
# Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
# """

#     for i, word in enumerate(word_timings):
#         try:
#             start = float(word["start"])
#             end = float(word["end"])
#             raw_text = str(word["word"])
#             text = clean_word(raw_text)

#             if not text or end <= 0 or start < 0:
#                 continue

#             if i + 1 < len(word_timings):
#                 next_start = float(word_timings[i + 1].get("start", end))
#                 end = min(end, next_start - safety_margin)

#             end = max(start + 0.01, min(end, start + max_duration))

#             start_str = seconds_to_ass_time(start)
#             end_str = seconds_to_ass_time(end)
#             style = "Emphasized" if is_emphasized(text) else "BoldCenter"

#             ass_content += f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{text}\n"

#         except Exception as e:
#             print(f"[ERROR] Skipping word due to parsing error: {word} — {e}")
#             continue

#     with open(subtitle_path, "w", encoding="utf-8") as f:
#         f.write(ass_content)

#     return subtitle_path

# if __name__ == "__main__":
#     date_str = datetime.now().strftime("%Y%m%d")
#     for name in ["1", "2", "3"]:
#         print(f"Word-by-word subtitles for story_{name}:", generate_subs(date_str, name))
