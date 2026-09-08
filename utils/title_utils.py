import json
import random
import google.generativeai as genai
import os
import re

HOOKS = ["INSANE", "KARMA", "REVENGE", "EXPOSED", "UNBELIEVABLE", "HEARTBREAKING", "SHOCKING", "TWISTED"]

def local_title_enhancer(title):
    if any(h.lower() in title.lower() for h in HOOKS):
        return title
    return f"{title} | {random.choice(HOOKS)}"

def clean_title_for_ffmpeg(title):
    title = title.split('\n')[0]
    title = re.sub(r'[^\x00-\x7F]+', '', title)
    title = re.sub(r'[\'":]', '', title)
    return title.strip()

GEMINI_CANDIDATE_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-2.5-pro",
    "gemini-pro-latest"
]

def generate_title_with_gemini(text, fallback_title):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return fallback_title

    genai.configure(api_key=api_key)
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

    models_to_try = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()] + [m for m in GEMINI_CANDIDATE_MODELS if m != os.environ.get("GEMINI_MODEL")]
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name=f"models/{model_name}" if not model_name.startswith("models/") else model_name)
            response = m.generate_content(prompt)
            if response and response.candidates and response.candidates[0].content.parts:
                gemini_title = response.candidates[0].content.parts[0].text.strip()
                cleaned = clean_title_for_ffmpeg(gemini_title)
                if cleaned:
                    return f"[{subreddit}] {cleaned}"
        except Exception:
            continue

    return fallback_title


def enhance_story_hook_with_gemini(text, subreddit="Reddit"):
    if not text or len(text) < 80:
        return text

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return text

    genai.configure(api_key=api_key)
    prompt = (
        f"You are a viral YouTube Shorts editor adapting a real story from r/{subreddit}.\n"
        "Task: Rewrite the opening 1-2 sentences of this story into an intense, punchy narrative hook.\n"
        "Rules:\n"
        "1. Remove boring intro filler like 'Throwaway account because...', 'Posting from mobile', 'Long time lurker'.\n"
        "2. Keep the narrator's authentic first-person perspective and exact facts.\n"
        "3. Output ONLY the complete revised story with your new opening hook seamlessly flowing into the remaining body.\n"
        "4. Do NOT add meta commentary, quotes, markdown formatting, or emojis.\n\n"
        f"Original Story:\n{text}"
    )

    models_to_try = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()] + [m for m in GEMINI_CANDIDATE_MODELS if m != os.environ.get("GEMINI_MODEL")]
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name=f"models/{model_name}" if not model_name.startswith("models/") else model_name)
            response = m.generate_content(prompt)
            if response and response.candidates and response.candidates[0].content.parts:
                enhanced_text = response.candidates[0].content.parts[0].text.strip()
                if enhanced_text and len(enhanced_text) >= len(text) * 0.7:
                    enhanced_text = re.sub(r'[^\x00-\x7F]+', '', enhanced_text).strip()
                    return enhanced_text
        except Exception:
            continue

    return text


def generate_conversation_short_script_with_gemini(raw_title, raw_text, subreddit="iMessage"):
    """
    Slot 1: Generates an intense, escalating 1 min 15s+ (190-250 words, 14-18 messages) full iMessage drama thread.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not raw_text or len(raw_text) < 60:
        return None

    genai.configure(api_key=api_key)
    prompt = f"""You are a master social drama screenwriter and YouTube Shorts creator.
Transform the following real conflict into an extended, intense, suspenseful 1 MINUTE 15 SECONDS+ (75-90 seconds) text message conversation short.

Requirements:
1. "title": Viral, clickable title under 55 chars (e.g. "My Landlord Sent This At 2 AM").
2. "hook": 1 opening sentence spoken as the premise hook (10-15 words, e.g. "When my landlord texted me at 2 AM, I never expected things to escalate this fast.").
3. "contact_name": The contact name for the iPhone header (e.g. "Landlord Dave", "Bridezilla Sarah", "Crazy Roommate", "Boss Mike", "Ex-Fiance").
4. "chat_messages": A list of 14 to 18 back-and-forth messages alternating between the contact and "Me".
   - Total spoken dialogue must be 190 to 250 words so the conversation lasts 75 to 90 seconds.
   - Escalating drama arc: unreasonable opening demand -> sharp pushback -> absurd justification -> revelation of evidence/receipts -> ultimate confrontation -> mic-drop ending.
   - Each message must have: "sender" (contact name or "Me"), "text" (the text line), "is_me" (bool).
5. "debate_question": 1 closing question asking viewers who was in the wrong and to comment/subscribe (e.g. "Whose side are you on? Drop your verdict below and subscribe for daily drama!").
6. "voice_gender": "male" or "female".

Output ONLY valid JSON matching this exact schema:
{{
  "title": "Title Here",
  "hook": "1-sentence hook premise here.",
  "contact_name": "Landlord Dave",
  "chat_messages": [
    {{"sender": "Landlord Dave", "text": "Are you awake? I need you to vacate the apartment by tomorrow morning.", "is_me": false}},
    {{"sender": "Me", "text": "Tomorrow? My lease is signed through December and rent is fully paid.", "is_me": true}},
    {{"sender": "Landlord Dave", "text": "My daughter is moving to town and needs the unit. Pack your things.", "is_me": false}},
    {{"sender": "Me", "text": "That is completely illegal. You cannot give 12 hours notice to evict a paying tenant.", "is_me": true}},
    {{"sender": "Landlord Dave", "text": "I own the building so I make the rules. I am changing the locks at noon.", "is_me": false}},
    {{"sender": "Me", "text": "I just forwarded your texts to the city housing authority and my lawyer.", "is_me": true}},
    {{"sender": "Landlord Dave", "text": "You wouldn't dare. Delete those screenshots immediately.", "is_me": false}},
    {{"sender": "Me", "text": "The inspector is already on their way. See you in court Dave.", "is_me": true}}
  ],
  "debate_question": "Whose side are you on? Drop your verdict below and subscribe for daily drama!",
  "voice_gender": "male"
}}

Raw Title: {raw_title}
Raw Story Text: {raw_text[:2800]}
"""
    models_to_try = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()] + [m for m in GEMINI_CANDIDATE_MODELS if m != os.environ.get("GEMINI_MODEL")]
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name=f"models/{model_name}" if not model_name.startswith("models/") else model_name)
            response = m.generate_content(prompt)
            if response and response.candidates and response.candidates[0].content.parts:
                raw_out = response.candidates[0].content.parts[0].text.strip()
                json_str = re.sub(r"^```json\s*", "", raw_out, flags=re.IGNORECASE)
                json_str = re.sub(r"\s*```$", "", json_str).strip()
                data = json.loads(json_str)
                if isinstance(data, dict) and data.get("chat_messages") and len(data["chat_messages"]) >= 6:
                    data["title"] = clean_title_for_ffmpeg(data.get("title", raw_title))
                    data["hook"] = clean_title_for_ffmpeg(data.get("hook", ""))
                    data["contact_name"] = clean_title_for_ffmpeg(data.get("contact_name", "Messages"))
                    data["story_format"] = "message_short"
                    return data
        except Exception:
            continue
    return None


def generate_psychological_case_script_with_gemini(raw_title, raw_text, subreddit="Reddit"):
    """
    Slot 2: Generates an in-depth 1 MINUTE+ (70-85s, 210-250 words) Psychological Case Study & Behavioral Analysis Short.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not raw_text or len(raw_text) < 60:
        return None

    genai.configure(api_key=api_key)
    prompt = f"""You are a master behavioral psychologist, social commentator, and YouTube Shorts creator.
Transform the following real dilemma from r/{subreddit} into a high-value, educational Case Study & Behavioral Breakdown video lasting 1 MINUTE+ (70-85 seconds total audio).

Structure requirements:
1. "title": Clickable YouTube title under 55 characters without emojis.
2. "hook": 1 sharp analytical thesis hook sentence spoken by the HOST (12-16 words).
3. "story": Detailed 1st-person dilemma facts spoken by the NARRATOR (90-115 words, 30-35s).
4. "key_quote": 1 pivotal statement from the conflict for the quotation card.
5. "quote_speaker": Name/role of person who said the quote (e.g., "Wife", "Mother-in-law", "Manager").
6. "red_flags": Array of 3 concise psychological patterns or boundary violations (e.g. ["Covert Expectation", "Weaponized Incompetence", "Boundary Erosion"]).
7. "analysis": In-depth psychological and ethical breakdown spoken by the HOST (90-115 words, 35-40s).
8. "debate_question": 1 thought-provoking debate question and subscribe CTA (e.g. "Who crossed the line here? Drop your verdict in the comments and subscribe for daily breakdowns!").
9. "voice_gender": "male" or "female".

Output ONLY valid JSON matching this schema:
{{
  "title": "Title Here",
  "hook": "Host thesis hook here.",
  "story": "Narrator detailed dilemma facts here.",
  "key_quote": "Pivotal quote here.",
  "quote_speaker": "Speaker Name",
  "red_flags": ["Pattern 1", "Pattern 2", "Pattern 3"],
  "analysis": "Host in-depth psychological analysis here.",
  "debate_question": "Who was in the wrong here? Drop your thoughts in the comments and subscribe for daily breakdowns!",
  "voice_gender": "male"
}}

Raw Title: {raw_title}
Raw Text: {raw_text[:3000]}
"""
    models_to_try = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()] + [m for m in GEMINI_CANDIDATE_MODELS if m != os.environ.get("GEMINI_MODEL")]
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name=f"models/{model_name}" if not model_name.startswith("models/") else model_name)
            response = m.generate_content(prompt)
            if response and response.candidates and response.candidates[0].content.parts:
                raw_out = response.candidates[0].content.parts[0].text.strip()
                json_str = re.sub(r"^```json\s*", "", raw_out, flags=re.IGNORECASE)
                json_str = re.sub(r"\s*```$", "", json_str).strip()
                data = json.loads(json_str)
                if isinstance(data, dict) and data.get("story") and data.get("analysis"):
                    data["title"] = clean_title_for_ffmpeg(data.get("title", raw_title))
                    data["hook"] = clean_title_for_ffmpeg(data.get("hook", ""))
                    data["story"] = clean_title_for_ffmpeg(data.get("story", ""))
                    data["key_quote"] = clean_title_for_ffmpeg(data.get("key_quote", ""))
                    data["quote_speaker"] = clean_title_for_ffmpeg(data.get("quote_speaker", "The Story"))
                    data["analysis"] = clean_title_for_ffmpeg(data.get("analysis", ""))
                    data["debate_question"] = clean_title_for_ffmpeg(data.get("debate_question", "Who was in the wrong here? Drop your thoughts in the comments and subscribe for daily breakdowns!"))
                    data["chat_messages"] = []
                    data["story_format"] = "breakdown_short"
                    return data
        except Exception:
            continue
    return None


def generate_moral_dilemma_script_with_gemini(raw_title, raw_text, subreddit="Reddit"):
    """
    Slot 3: Generates a high-stakes 1 MINUTE 30 SECONDS+ (95-115s, 270-320 words) Moral Dilemma Court Short.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not raw_text or len(raw_text) < 60:
        return None

    genai.configure(api_key=api_key)
    prompt = f"""You are a master social commentator and YouTube Shorts creator.
Transform the following real dilemma from r/{subreddit} into a high-engagement Moral Dilemma Court video lasting 1 MINUTE 30 SECONDS+ (95 to 115 seconds total audio).

Structure requirements:
1. "title": Clickable title under 55 characters without emojis.
2. "hook": 1 intriguing ethical dilemma hook spoken by the HOST (12-16 words).
3. "story": Detailed 1st-person dilemma facts spoken by the NARRATOR (170-210 words, 55-65s).
4. "analysis": In-depth ethical breakdown analyzing both perspectives spoken by the HOST (60-80 words, 20-25s).
5. "verdict_title": Short verdict header (e.g. "WHO IS WRONG?", "IS OP THE JERK?").
6. "opt_a": Option A label (e.g. "NOT THE JERK", "JUSTIFIED").
7. "pct_a": Option A community percentage (integer 60 to 90).
8. "opt_b": Option B label (e.g. "AT FAULT", "OVERREACTING").
9. "pct_b": Option B community percentage (integer 100 - pct_a).
10. "takeaway": 1 concise community takeaway principle (under 12 words).
11. "debate_question": 1 direct question asking the viewer to judge in the comments and subscribe (e.g. "Who was in the wrong here? Drop your verdict in the comments below, and subscribe for daily moral dilemma court!").
12. "voice_gender": "male" or "female".

Output ONLY valid JSON matching this schema:
{{
  "title": "Title Here",
  "hook": "Host ethical hook here.",
  "story": "Narrator detailed dilemma facts here.",
  "analysis": "Host ethical breakdown here.",
  "verdict_title": "WHO IS IN THE WRONG?",
  "opt_a": "NOT THE JERK",
  "pct_a": 84,
  "opt_b": "AT FAULT",
  "pct_b": 16,
  "takeaway": "Family boundaries must come before family guilt.",
  "debate_question": "Who was in the wrong here? Drop your verdict in the comments below, and subscribe for daily moral dilemma court!",
  "voice_gender": "male"
}}

Raw Title: {raw_title}
Raw Text: {raw_text[:3500]}
"""
    models_to_try = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()] + [m for m in GEMINI_CANDIDATE_MODELS if m != os.environ.get("GEMINI_MODEL")]
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name=f"models/{model_name}" if not model_name.startswith("models/") else model_name)
            response = m.generate_content(prompt)
            if response and response.candidates and response.candidates[0].content.parts:
                raw_out = response.candidates[0].content.parts[0].text.strip()
                json_str = re.sub(r"^```json\s*", "", raw_out, flags=re.IGNORECASE)
                json_str = re.sub(r"\s*```$", "", json_str).strip()
                data = json.loads(json_str)
                if isinstance(data, dict) and data.get("story") and data.get("opt_a"):
                    data["title"] = clean_title_for_ffmpeg(data.get("title", raw_title))
                    data["hook"] = clean_title_for_ffmpeg(data.get("hook", ""))
                    data["story"] = clean_title_for_ffmpeg(data.get("story", ""))
                    data["analysis"] = clean_title_for_ffmpeg(data.get("analysis", ""))
                    data["debate_question"] = clean_title_for_ffmpeg(data.get("debate_question", "Who was in the wrong here? Drop your verdict in the comments below, and subscribe for daily moral dilemma court!"))
                    data["chat_messages"] = []
                    data["red_flags"] = []
                    data["story_format"] = "verdict_short"
                    return data
        except Exception:
            continue
    return None

# Unified entrypoint router based on slot
def generate_transformative_script_with_gemini(raw_title, raw_text, subreddit="Reddit", slot=1):
    if slot == 1:
        return generate_conversation_short_script_with_gemini(raw_title, raw_text, subreddit=subreddit)
    elif slot == 2:
        return generate_psychological_case_script_with_gemini(raw_title, raw_text, subreddit=subreddit)
    else:
        return generate_moral_dilemma_script_with_gemini(raw_title, raw_text, subreddit=subreddit)
