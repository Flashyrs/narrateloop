import os
import sys
import psutil
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import TimedOut
import time
from threading import Thread
from dotenv import load_dotenv

# --- Startup time tracking ---
startup_start_time = datetime.now()

# scripts/telegram_notify.py
active_flags = {
    "tts": True,
    "subs": True,
    "render": True,
    "upload": True
}

def get_task_flags():
    return active_flags



# --- Prevent duplicate script execution ---
def already_running():
    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)
    with open("startup_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[DEBUG] Current PID: {current_pid}, script: {current_script}\n")

    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            pid = proc.info['pid']
            cmdline = proc.info['cmdline']
            if not cmdline:
                continue

            # DEBUG PRINT
            with open("startup_debug.log", "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] Checking PID {pid}, CMD: {cmdline}\n")

            # ✅ Skip this script itself
            if pid == current_pid or any(os.path.abspath(part) == current_script for part in cmdline if part.endswith('.py')):
                continue

            # ✅ Match only other instances of same script
            if any("telegram_notify.py" in part.lower() for part in cmdline):
                with open("startup_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"[INFO] Detected duplicate instance: PID {pid}, CMD: {cmdline}\n")
                return True
        except Exception as e:
            with open("startup_debug.log", "a", encoding="utf-8") as f:
                f.write(f"[ERROR] Failed checking process {proc}: {e}\n")
            continue
    return False





# Allow --force override from command line
if "--force" not in sys.argv and already_running():
    print("[INFO] Another instance is already running. Exiting.")
    sys.exit(0)

load_dotenv()

with open("startup_debug.log", "a", encoding="utf-8") as f:
    f.write(f"Started from Task Scheduler at {datetime.now()}\n")

LOG_FILE = f"logs/{datetime.now().strftime('%Y%m%d')}.log"
PIPELINE_ENABLED = True
should_stop = False
is_running = False

_last_edit_message_id = None
_last_edit_chat_id = None
_last_progress_text = None
_startup_message_id = None
_startup_chat_id = None


def edit_progress_message(new_text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not _last_edit_chat_id or _last_edit_message_id is None:
        return

    global _last_progress_text
    if new_text == _last_progress_text:
        return

    url = f"https://api.telegram.org/bot{token}/editMessageText"
    try:
        resp = requests.post(url, data={
            "chat_id": _last_edit_chat_id,
            "message_id": _last_edit_message_id,
            "text": new_text,
            "parse_mode": "Markdown"
        })
        if resp.ok:
            _last_progress_text = new_text
    except Exception as e:
        print(f"[Telegram] Failed to edit message: {e}")



# --- Telegram utilities ---
def send_telegram_log(message, tts_progress=False):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in env.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": message})

    if tts_progress and resp.ok:
        global _last_edit_message_id, _last_edit_chat_id, _last_progress_text
        try:
            msg_data = resp.json()
            _last_edit_message_id = msg_data["result"]["message_id"]
            _last_edit_chat_id = chat_id
            _last_progress_text = message
        except Exception as e:
            print(f"[Telegram] Error parsing message_id for edit: {e}")

# --- Startup status updates ---
def send_startup_status(text, initial=False):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    url_send = f"https://api.telegram.org/bot{token}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{token}/editMessageText"

    global _startup_message_id, _startup_chat_id

    if initial or _startup_message_id is None:
        try:
            resp = requests.post(url_send, data={"chat_id": chat_id, "text": text})
            if resp.ok:
                data = resp.json()
                _startup_message_id = data["result"]["message_id"]
                _startup_chat_id = chat_id
        except:
            pass
    else:
        try:
            requests.post(url_edit, data={
                "chat_id": _startup_chat_id,
                "message_id": _startup_message_id,
                "text": text
            })
        except:
            pass

# --- Logging ---
def log(message, telegram=False, tts_progress=False):
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    full_message = f"{timestamp} {message}"

    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(full_message + "\n")

    print(full_message)

    if telegram and tts_progress:
        send_telegram_log(full_message, tts_progress=True)
    elif telegram:
        send_telegram_log(full_message)

def clear_progress_state():
    global _last_edit_message_id, _last_edit_chat_id, _last_progress_text
    _last_edit_message_id = None
    _last_edit_chat_id = None
    _last_progress_text = None

async def safe_reply(update: Update, text: str):
    try:
        await update.message.reply_text(text)
    except TimedOut:
        log("Reply to Telegram timed out.")
    except Exception as e:
        log(f"Reply failed: {e}")

def schedule_uploads():
    from main_pipeline import run_pipeline_upload_specific  # import here to avoid circular issues

    def loop():
        last_sent = ""
        while True:
            now = datetime.now().strftime("%H:%M")
            if now != last_sent:
                for hour, story_num in {"10:00": 1, "16:00": 2, "21:00": 3}.items():
                    if now == hour:
                        send_telegram_log(f"⏰ Auto upload trigger: story_{story_num}.json")

                        def run():
                            global is_running
                            is_running = True
                            try:
                                run_pipeline_upload_specific(story_num)
                            except Exception as e:
                                log(f"[AutoUpload] Error uploading story {story_num}: {e}")
                            finally:
                                is_running = False
                                clear_progress_state()

                        Thread(target=run, daemon=True).start()
                last_sent = now
            time.sleep(30)

    Thread(target=loop, daemon=True).start()


def load_pipeline():
    from main_pipeline import run_pipeline, run_pipeline_upload_specific, get_upload_status, active_flags
    return run_pipeline, run_pipeline_upload_specific, get_upload_status, active_flags

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Missing TELEGRAM_BOT_TOKEN in environment.")
        sys.exit(1)

    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, ROOT_DIR)

    app = ApplicationBuilder().token(TOKEN).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global should_stop, is_running
        should_stop = False
        if is_running:
            await safe_reply(update, "Already running.")
            return

        is_running = True
        await safe_reply(update, "Starting processing...")
        run_pipeline, _, _, _ = load_pipeline()

        def run():
            try:
                run_pipeline(upload=False)
            except Exception as e:
                log(f"Pipeline error during start: {e}")
            finally:
                global is_running
                is_running = False
                clear_progress_state()
                log("Processing complete. Waiting for command...")

        asyncio.get_event_loop().run_in_executor(None, run)

    async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global should_stop
        should_stop = True
        await safe_reply(update, "Processing will stop after current task.")

    async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global is_running
        if is_running:
            await safe_reply(update, "Already processing. Try again later.")
            return

        try:
            if not context.args:
                await safe_reply(update, "Usage: /upload 1 or /upload 2 or /upload 3")
                return
            story_num = int(context.args[0])
        except Exception as e:
            await safe_reply(update, f"Error parsing command: {e}")
            return

        is_running = True
        await safe_reply(update, f"Uploading video for story_{story_num}.json...")
        _, run_pipeline_upload_specific, _, _ = load_pipeline()

        def run():
            try:
                run_pipeline_upload_specific(story_num)
            except Exception as e:
                log(f"Upload command error: {e}")
            finally:
                global is_running
                is_running = False
                clear_progress_state()

        asyncio.get_event_loop().run_in_executor(None, run)

    async def task_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _, _, _, active_flags = load_pipeline()
        lines = [f"{task.upper()}: {'🟢 ON' if state else '🔴 OFF'}" for task, state in active_flags.items()]
        await safe_reply(update, "⚙️ Current Task Status:\n" + "\n".join(lines))


    async def control_task(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        _, _, _, active_flags = load_pipeline()

        if not context.args:
            await safe_reply(update, f"Usage: /{action}task [tts|subs|render|upload]")
            return

        task = context.args[0].lower()
        if task not in active_flags:
            await safe_reply(update, f"Invalid task. Valid: {', '.join(active_flags.keys())}")
            return

        active_flags[task] = True if action == "start" else False
        await safe_reply(update, f"✅ `{task.upper()}` {'enabled' if action == 'start' else 'disabled'}.")

    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _, _, get_upload_status, _ = load_pipeline()

        try:
            date_str = context.args[0] if context.args else datetime.now().strftime('%Y%m%d')
            status_text = get_upload_status(date_str)
            await safe_reply(update, status_text)
        except Exception as e:
            await safe_reply(update, f"Error fetching status: {e}")



    async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now().strftime("%Y%m%d")
        log_path = f"logs/{today}.log"
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()[-4000:]
            await safe_reply(update, content)
        else:
            await safe_reply(update, "No logs found for today.")

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await safe_reply(update,
            "/start - Start processing pipeline\n"
            "/upload [n] - Upload specific story number\n"
            "/stop - Stop after current task\n"
            "/status [YYYYMMDD] - List uploadable and uploaded videos\n"
            "/log - Show latest logs\n"
            "/uptime - Show how long the bot has been running\n"
            "/starttask [stage] - Enable a pipeline stage\n"
            "/stoptask [stage] - Disable a pipeline stage\n"
            "/taskstatus - Show enabled/disabled stages\n"
            "/help - Show this help message"
        )

    async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
        now = datetime.now()
        uptime_duration = now - startup_start_time
        human_readable = str(timedelta(seconds=int(uptime_duration.total_seconds())))
        await safe_reply(update, f"🕒 Uptime: {human_readable}")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("taskstatus", task_status_command))
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("uptime", uptime))
    app.add_handler(CommandHandler("starttask", lambda u, c: control_task(u, c, "start")))
    app.add_handler(CommandHandler("stoptask", lambda u, c: control_task(u, c, "stop")))

    def startup_run():
        try:
            send_startup_status("🚀 Initializing, please wait...", initial=True)
            log("Starting processing in background...", telegram=True)
            run_pipeline, _, _, _ = load_pipeline()
            start = time.time()
            Thread(target=run_pipeline, kwargs={"upload": False}, daemon=True).start()
            elapsed = time.time() - start
            log("Pipeline launched. Waiting for commands...", telegram=True)
            send_startup_status(f"✅ Startup complete in {elapsed:.2f} seconds. Ready for commands!")
        except Exception as e:
            log(f"Startup pipeline error: {e}")
            with open("startup_debug.log", "a", encoding="utf-8") as f:
                f.write(f"Startup error: {e}\n")

    asyncio.get_event_loop().run_in_executor(None, startup_run)
    print("Telegram bot is now running. You can send commands.")
    schedule_uploads()
    app.run_polling()
    log("❌ Script ended unexpectedly or completed execution")
    send_telegram_log("❌ NarrateLoopBot stopped or exited")

