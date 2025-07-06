import os
import json
import warnings
from datetime import datetime
import time
import torch
import re
import numpy as np
import traceback
import GPUtil
import whisper_timestamped as whisper
import pickle
import ctypes

from bark import generation, preload_models
from scripts.telegram_notify import log, clear_progress_state, edit_progress_message

# Prevent system sleep
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040  # For multimedia apps

def prevent_sleep():
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    )

def allow_sleep():
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

preload_models(text_use_gpu=True, coarse_use_gpu=True, fine_use_gpu=True, codec_use_gpu=True)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

punkt_path = os.path.join(PROJECT_ROOT, "nltk_data", "tokenizers", "punkt", "english.pickle")
with open(punkt_path, "rb") as f:
    tokenizer = pickle.load(f)

BARK_ROOT = os.path.dirname(generation.__file__)
USE_GOOGLE_TTS = False

SPEAKER_PRESETS = {
    "male": ["v2/en_speaker_7", "v2/en_speaker_8", "v2/en_speaker_9"],
    "female": ["v2/en_speaker_0", "v2/en_speaker_1", "v2/en_speaker_2"]
}

if not hasattr(torch.serialization, "safe_globals"):
    warnings.warn("Patching torch.serialization to handle weights_only=True for backward compatibility")
    from contextlib import contextmanager
    @contextmanager
    def dummy_safe_globals(*args, **kwargs):
        yield
    torch.serialization.safe_globals = dummy_safe_globals

def detect_gender(text):
    matches = re.findall(r"\b\d{1,2}[MF]\b", text.upper())
    genders = [m[-1] for m in matches]
    if not genders:
        return "male"
    return "female" if genders.count("F") > genders.count("M") else "male"

def clean_text_for_bark(text):
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2026", "...")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    return text

class TelegramProgress:
    def __init__(self, total_chunks, story_file, threshold_percent=2):
        self.total = total_chunks
        self.current = 0
        self.story_file = story_file
        self.last_percent = -1
        self.threshold_percent = threshold_percent
        self.bar_length = 20
        self._first_update_done = False

    def _build_bar(self, percent):
        filled = int((percent / 100) * self.bar_length)
        unfilled = self.bar_length - filled
        return f"{'▰' * filled}{'▱' * unfilled} {percent}%"

    def update(self):
        self.current += 1
        percent = int((self.current / self.total) * 100)
        if self.last_percent == -1 or (percent - self.last_percent) >= self.threshold_percent:
            self.last_percent = percent
            bar_text = f"[{self.story_file}]  TTS progress: {self._build_bar(percent)}"
            if not self._first_update_done:
                log(bar_text, telegram=True, tts_progress=True)
                self._first_update_done = True
            else:
                edit_progress_message(bar_text)

    def done(self):
        final_text = f"[{self.story_file}]  TTS complete"
        edit_progress_message(final_text)
        log(final_text, telegram=True, tts_progress=False)
        clear_progress_state()

def log_gpu_usage():
    try:
        gpus = GPUtil.getGPUs()
        for gpu in gpus:
            log(f"GPU: {gpu.name}, Used: {gpu.memoryUsed}MB / {gpu.memoryTotal}MB", telegram=True)
    except Exception as e:
        log(f"GPU usage check failed: {e}", telegram=True)

def _load_history_prompt(history_prompt_input):
    ALLOWED_PROMPTS = SPEAKER_PRESETS["male"] + SPEAKER_PRESETS["female"]
    if isinstance(history_prompt_input, str) and history_prompt_input.endswith(".npz"):
        return {k: v for k, v in np.load(history_prompt_input).items()}
    elif isinstance(history_prompt_input, str):
        if history_prompt_input not in ALLOWED_PROMPTS:
            raise ValueError(f"history prompt not found: {history_prompt_input}")
        path = os.path.join(BARK_ROOT, "assets", "prompts", f"{history_prompt_input}.npz")
        return {k: v for k, v in np.load(path).items()}
    elif isinstance(history_prompt_input, dict):
        assert "semantic_prompt" in history_prompt_input
        return history_prompt_input
    else:
        raise ValueError("history prompt format unrecognized")

def tts_google(text, out_path):
    from google.cloud import texttospeech
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/google-tts-key.json"
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    with open(out_path, "wb") as out:
        out.write(response.audio_content)

def generate_word_timings(audio_path, output_json_path):
    prevent_sleep()
    try:
        model_name = "medium"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log(f"[{datetime.now().strftime('%Y%m%d')}] Loading Whisper '{model_name}' model on {device.upper()}...")

        try:
            model = whisper.load_model(model_name, device=device)
            if device == "cuda":
                log_gpu_usage()
        except RuntimeError as e:
            if "CUDA out of memory" in str(e):
                log("CUDA OOM — falling back to CPU")
                model = whisper.load_model(model_name, device="cpu")
            else:
                log(f"Whisper load failed:\n{traceback.format_exc()}")
                raise

        result = whisper.transcribe(model, audio_path, language="en", vad="silero")
        words = [{"word": w["text"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
                 for seg in result["segments"] for w in seg["words"]]

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)
    finally:
        allow_sleep()

def tts_bark(text, out_path, voice_preset, story_name):
    from bark import generate_audio
    from scipy.io.wavfile import write as write_wav
    from pydub import AudioSegment
    from pydub.effects import normalize
    import tempfile

    prevent_sleep()
    try:
        def split_text(text, max_words=60):
            sentences = tokenizer.tokenize(text)
            chunks, current = [], []
            for sentence in sentences:
                words = sentence.split()
                if len(current) + len(words) <= max_words:
                    current.extend(words)
                else:
                    chunks.append(" ".join(current))
                    current = words
            if current:
                chunks.append(" ".join(current))
            return chunks

        def speed_up_audio(audio: AudioSegment, speed: float = 1.3) -> AudioSegment:
            new_frame_rate = int(audio.frame_rate * speed)
            sped_up = audio._spawn(audio.raw_data, overrides={'frame_rate': new_frame_rate})
            return sped_up.set_frame_rate(audio.frame_rate)

        history_prompt = _load_history_prompt(voice_preset)
        chunks = split_text(text)
        combined = AudioSegment.silent(duration=200)
        progress = TelegramProgress(total_chunks=len(chunks), story_file=f"story_{story_name}.json")

        for idx, chunk in enumerate(chunks):
            print(f" Generating chunk {idx + 1}/{len(chunks)}")
            audio_array = generate_audio(chunk, history_prompt=history_prompt)
            audio_array = np.clip(audio_array, -1.0, 1.0)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                write_wav(tmpfile.name, 24000, (audio_array * 32767).astype(np.int16))
                segment = AudioSegment.from_wav(tmpfile.name)
                segment = normalize(segment) if idx == 0 else normalize(segment.fade_in(50).fade_out(50))
                combined += segment
            progress.update()

        progress.done()
        combined = speed_up_audio(combined, speed=1.3)
        combined.export(out_path, format="wav")
    finally:
        allow_sleep()

def generate_tts(date_str, story_name):
    story_folder = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
    audio_dir = os.path.join(PROJECT_ROOT, "audio", date_str)
    os.makedirs(audio_dir, exist_ok=True)

    story_path = os.path.join(story_folder, f"story_{story_name}.json")
    out_path = os.path.join(audio_dir, f"voice_{story_name}.wav")
    timing_path = out_path.replace(".wav", "_timing.json")

    if os.path.exists(out_path) and os.path.exists(timing_path):
        print(f" TTS and timings already exist for story {story_name}, skipping...")
        return out_path

    with open(story_path, "r", encoding="utf-8") as f:
        story = json.load(f)

    full_text = story['text'].strip().replace("\n", " ")
    full_text = clean_text_for_bark(full_text)

    if USE_GOOGLE_TTS:
        out_path = out_path.replace(".wav", ".mp3")
        tts_google(full_text, out_path)
    else:
        voice_gender = story.get("voice")
        if voice_gender not in ["male", "female"]:
            combined_text = story.get("title", "") + " " + story.get("text", "")
            voice_gender = detect_gender(combined_text)
            story["voice"] = voice_gender
            with open(story_path, "w", encoding="utf-8") as f:
                json.dump(story, f, indent=4, ensure_ascii=False)

        voice_preset = "v2/en_speaker_9" if voice_gender == "female" else "v2/en_speaker_0"
        log(f"[story_{story_name}] Using voice preset: {voice_preset}", telegram=True)
        tts_bark(full_text, out_path, voice_preset, story_name)
        generate_word_timings(out_path, timing_path)

if __name__ == "__main__":
    date_str = datetime.now().strftime("%Y%m%d")
    for name in ["1", "2", "3"]:
        generate_tts(date_str, story_name=name)





# import os
# import json
# import warnings
# from datetime import datetime
# import time
# import torch
# import re
# import numpy as np
# import traceback
# import GPUtil
# import whisper_timestamped as whisper
# import pickle

# from bark import generation, preload_models
# from telegram_notify import log, clear_progress_state, edit_progress_message

# preload_models(text_use_gpu=True, coarse_use_gpu=True, fine_use_gpu=True, codec_use_gpu=True)

# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# punkt_path = os.path.join(PROJECT_ROOT, "nltk_data", "tokenizers", "punkt", "english.pickle")
# with open(punkt_path, "rb") as f:
#     tokenizer = pickle.load(f)

# BARK_ROOT = os.path.dirname(generation.__file__)
# USE_GOOGLE_TTS = False

# SPEAKER_PRESETS = {
#     "male": ["v2/en_speaker_7", "v2/en_speaker_8", "v2/en_speaker_9"],
#     "female": ["v2/en_speaker_0", "v2/en_speaker_1", "v2/en_speaker_2"]
# }

# if not hasattr(torch.serialization, "safe_globals"):
#     warnings.warn("Patching torch.serialization to handle weights_only=True for backward compatibility")
#     from contextlib import contextmanager
#     @contextmanager
#     def dummy_safe_globals(*args, **kwargs):
#         yield
#     torch.serialization.safe_globals = dummy_safe_globals

# def detect_gender(text):
#     matches = re.findall(r"\b\d{1,2}[MF]\b", text.upper())
#     genders = [m[-1] for m in matches]
#     if not genders:
#         return "male"
#     return "female" if genders.count("F") > genders.count("M") else "male"

# def clean_text_for_bark(text):
#     text = text.replace("\u201c", '"').replace("\u201d", '"')
#     text = text.replace("\u2018", "'").replace("\u2019", "'")
#     text = text.replace("\u2013", "-").replace("\u2014", "-")
#     text = text.replace("\u2026", "...")
#     text = text.replace("\xa0", " ")
#     text = re.sub(r"[^\x00-\x7F]+", "", text)
#     return text

# class TelegramProgress:
#     def __init__(self, total_chunks, story_file, threshold_percent=2):
#         self.total = total_chunks
#         self.current = 0
#         self.story_file = story_file
#         self.last_percent = -1
#         self.threshold_percent = threshold_percent
#         self.bar_length = 20
#         self._first_update_done = False

#     def _build_bar(self, percent):
#         filled = int((percent / 100) * self.bar_length)
#         unfilled = self.bar_length - filled
#         return f"{'▰' * filled}{'▱' * unfilled} {percent}%"

#     def update(self):
#         self.current += 1
#         percent = int((self.current / self.total) * 100)
#         if self.last_percent == -1 or (percent - self.last_percent) >= self.threshold_percent:
#             self.last_percent = percent
#             bar_text = f"[{self.story_file}]  TTS progress: {self._build_bar(percent)}"
#             if not self._first_update_done:
#                 log(bar_text, telegram=True, tts_progress=True)
#                 self._first_update_done = True
#             else:
#                 edit_progress_message(bar_text)

#     def done(self):
#         final_text = f"[{self.story_file}]  TTS complete"
#         edit_progress_message(final_text)
#         log(final_text, telegram=True, tts_progress=False)
#         clear_progress_state()

# def log_gpu_usage():
#     try:
#         gpus = GPUtil.getGPUs()
#         for gpu in gpus:
#             log(f"GPU: {gpu.name}, Used: {gpu.memoryUsed}MB / {gpu.memoryTotal}MB", telegram=True)
#     except Exception as e:
#         log(f"GPU usage check failed: {e}", telegram=True)

# def _load_history_prompt(history_prompt_input):
#     ALLOWED_PROMPTS = SPEAKER_PRESETS["male"] + SPEAKER_PRESETS["female"]
#     if isinstance(history_prompt_input, str) and history_prompt_input.endswith(".npz"):
#         return {k: v for k, v in np.load(history_prompt_input).items()}
#     elif isinstance(history_prompt_input, str):
#         if history_prompt_input not in ALLOWED_PROMPTS:
#             raise ValueError(f"history prompt not found: {history_prompt_input}")
#         path = os.path.join(BARK_ROOT, "assets", "prompts", f"{history_prompt_input}.npz")
#         return {k: v for k, v in np.load(path).items()}
#     elif isinstance(history_prompt_input, dict):
#         assert "semantic_prompt" in history_prompt_input
#         return history_prompt_input
#     else:
#         raise ValueError("history prompt format unrecognized")

# def tts_google(text, out_path):
#     from google.cloud import texttospeech
#     os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/google-tts-key.json"
#     client = texttospeech.TextToSpeechClient()
#     synthesis_input = texttospeech.SynthesisInput(text=text)
#     voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
#     audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
#     response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
#     with open(out_path, "wb") as out:
#         out.write(response.audio_content)

# def generate_word_timings(audio_path, output_json_path):
#     model_name = "medium"
#     device = "cuda" if torch.cuda.is_available() else "cpu"
#     log(f"[{datetime.now().strftime('%Y%m%d')}] Loading Whisper '{model_name}' model on {device.upper()}...")

#     try:
#         model = whisper.load_model(model_name, device=device)
#         if device == "cuda":
#             log_gpu_usage()
#     except RuntimeError as e:
#         if "CUDA out of memory" in str(e):
#             log("CUDA OOM — falling back to CPU")
#             model = whisper.load_model(model_name, device="cpu")
#         else:
#             log(f"Whisper load failed:\n{traceback.format_exc()}")
#             raise

#     result = whisper.transcribe(model, audio_path, language="en", vad="silero")
#     words = [{"word": w["text"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
#              for seg in result["segments"] for w in seg["words"]]

#     with open(output_json_path, "w", encoding="utf-8") as f:
#         json.dump(words, f, ensure_ascii=False, indent=2)

# def tts_bark(text, out_path, voice_preset, story_name):
#     from bark import generate_audio
#     from scipy.io.wavfile import write as write_wav
#     from pydub import AudioSegment
#     from pydub.effects import normalize
#     import tempfile

#     def split_text(text, max_words=60):
#         sentences = tokenizer.tokenize(text)
#         chunks, current = [], []
#         for sentence in sentences:
#             words = sentence.split()
#             if len(current) + len(words) <= max_words:
#                 current.extend(words)
#             else:
#                 chunks.append(" ".join(current))
#                 current = words
#         if current:
#             chunks.append(" ".join(current))
#         return chunks

#     def speed_up_audio(audio: AudioSegment, speed: float = 1.3) -> AudioSegment:
#         """Speeds up the audio by a factor without changing pitch drastically."""
#         new_frame_rate = int(audio.frame_rate * speed)
#         sped_up = audio._spawn(audio.raw_data, overrides={'frame_rate': new_frame_rate})
#         return sped_up.set_frame_rate(audio.frame_rate)

#     history_prompt = _load_history_prompt(voice_preset)
#     chunks = split_text(text)
#     combined = AudioSegment.silent(duration=200)

#     progress = TelegramProgress(total_chunks=len(chunks), story_file=f"story_{story_name}.json")

#     for idx, chunk in enumerate(chunks):
#         print(f" Generating chunk {idx + 1}/{len(chunks)}")
#         audio_array = generate_audio(chunk, history_prompt=history_prompt)
#         audio_array = np.clip(audio_array, -1.0, 1.0)
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
#             write_wav(tmpfile.name, 24000, (audio_array * 32767).astype(np.int16))
#             segment = AudioSegment.from_wav(tmpfile.name)
#             segment = normalize(segment) if idx == 0 else normalize(segment.fade_in(50).fade_out(50))
#             combined += segment
#         progress.update()

#     progress.done()

#     # 🟢 Speed up the final combined audio
#     combined = speed_up_audio(combined, speed=1.3)  # Adjust 1.25 to make it faster/slower

#     combined.export(out_path, format="wav")


# def generate_tts(date_str, story_name):
#     story_folder = os.path.join(PROJECT_ROOT, "reddit_stories", date_str)
#     audio_dir = os.path.join(PROJECT_ROOT, "audio", date_str)
#     os.makedirs(audio_dir, exist_ok=True)

#     story_path = os.path.join(story_folder, f"story_{story_name}.json")
#     out_path = os.path.join(audio_dir, f"voice_{story_name}.wav")
#     timing_path = out_path.replace(".wav", "_timing.json")

#     if os.path.exists(out_path) and os.path.exists(timing_path):
#         print(f" TTS and timings already exist for story {story_name}, skipping...")
#         return out_path

#     with open(story_path, "r", encoding="utf-8") as f:
#         story = json.load(f)

#     full_text = story['text'].strip().replace("\n", " ")
#     full_text = clean_text_for_bark(full_text)

 

#     if USE_GOOGLE_TTS:
#         out_path = out_path.replace(".wav", ".mp3")
#         tts_google(full_text, out_path)
#     else:
#         voice_gender = story.get("voice")
#         if voice_gender not in ["male", "female"]:
#             combined_text = story.get("title", "") + " " + story.get("text", "")
#             voice_gender = detect_gender(combined_text)
#             story["voice"] = voice_gender
#             with open(story_path, "w", encoding="utf-8") as f:
#                 json.dump(story, f, indent=4, ensure_ascii=False)

#         # 🛠 Fixed preset selection
#         if voice_gender == "female":
#             voice_preset = "v2/en_speaker_9"
#         elif voice_gender == "male":
#             voice_preset = "v2/en_speaker_0"
#         else:
#             voice_preset = "v2/en_speaker_0"

#         log(f"[story_{story_name}] Using voice preset: {voice_preset}", telegram=True)

#         tts_bark(full_text, out_path, voice_preset, story_name)
#         generate_word_timings(out_path, timing_path)


# if __name__ == "__main__":
#     date_str = datetime.now().strftime("%Y%m%d")
#     for name in ["1", "2", "3"]:
#         generate_tts(date_str, story_name=name)
