import os
import sys
import psutil
import requests
import asyncio
from datetime import datetime, timedelta
try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    from telegram.error import TimedOut
except ImportError:
    from unittest.mock import MagicMock
    Update = MagicMock
    ApplicationBuilder = CommandHandler = MagicMock
    ContextTypes = MagicMock()
    TimedOut = Exception
import time
from threading import Thread
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=4.0)
    except Exception as e:
        print(f"[Telegram] Failed to send log: {e}")
        return

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

async def safe_reply(update: Update, text: str, parse_mode: str = None):
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except TimedOut:
        log("Reply to Telegram timed out.")
    except Exception as e:
        try:
            await update.message.reply_text(text)
        except Exception as e2:
            log(f"Reply failed: {e2}")

def get_current_time():
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()

def get_upload_schedule():
    custom_sched = os.getenv("UPLOAD_SCHEDULE")
    if custom_sched:
        try:
            return {str(k).strip(): int(v) for k, v in json.loads(custom_sched).items()}
        except Exception:
            pass
    custom_times = os.getenv("UPLOAD_TIMES")
    if custom_times:
        times = [t.strip() for t in custom_times.split(",") if t.strip()]
        if len(times) == 3:
            return {times[0]: 2, times[1]: 3, times[2]: 1}
        return {t: i + 1 for i, t in enumerate(times)}
    return {"10:00": 2, "16:00": 3, "21:00": 1}

def schedule_uploads():
    from main_pipeline import run_pipeline_upload_specific, run_pipeline  

    def loop():
        last_sent = ""
        last_daily_date = ""
        while True:
            current_dt = get_current_time()
            now = current_dt.strftime("%H:%M")
            today_str = current_dt.strftime("%Y%m%d")

            # 1. Daily automated pipeline run (Default 02:00 IST)
            daily_trigger_time = os.getenv("DAILY_RUN_TIME", "02:00")
            if now == daily_trigger_time and today_str != last_daily_date:
                last_daily_date = today_str
                send_telegram_log(f"🌙 Starting automated daily pipeline for {today_str}...")

                def run_daily():
                    global is_running
                    is_running = True
                    try:
                        run_pipeline(upload=False)
                    except Exception as e:
                        log(f"[DailyPipeline] Error in daily pipeline run: {e}")
                    finally:
                        is_running = False
                        clear_progress_state()

                Thread(target=run_daily, daemon=True).start()

            # 2. Scheduled video uploads (10:00, 16:00, 21:00 IST)
            if now != last_sent:
                schedule_map = get_upload_schedule()
                for hour, story_num in schedule_map.items():
                    if now == hour:
                        send_telegram_log(f"⏰ Auto upload trigger: story_{story_num}.json (Time: {now})")

                        def run(sn=story_num):
                            global is_running
                            is_running = True
                            try:
                                from utils.youtube_utils import get_youtube_auth_status
                                auth_check = get_youtube_auth_status()
                                if auth_check.get("status") in ["missing", "expired", "corrupt", "invalid"]:
                                    send_telegram_log(
                                        f"🚨 <b>Scheduled Upload Alert (Time: {now}):</b>\n\n"
                                        f"⚠️ Cannot upload story_{sn}.json because YouTube authentication is expired or missing.\n\n"
                                        f"👉 <b>Please re-authenticate now:</b>\n"
                                        f"Send <code>/auth_youtube</code> in this chat."
                                    )
                                    return

                                run_pipeline_upload_specific(sn)
                            except Exception as e:
                                err_str = str(e)
                                log(f"[AutoUpload] Error uploading story {sn}: {err_str}")
                                if "YouTube token" in err_str or "re-authenticate" in err_str or "RefreshError" in err_str:
                                    send_telegram_log(
                                        f"🚨 <b>YouTube Upload Failed: Authentication Expired</b>\n\n"
                                        f"Automated upload for story_{sn}.json was paused.\n\n"
                                        f"👉 <b>To re-authenticate now:</b>\n"
                                        f"Send <code>/auth_youtube</code> in this chat."
                                    )
                            finally:
                                is_running = False
                                clear_progress_state()

                        Thread(target=run, daemon=True).start()
                last_sent = now
            time.sleep(25)

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

    def is_authorized(update: Update) -> bool:
        """Verifies that the incoming update originates from an authorized TELEGRAM_CHAT_ID."""
        allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not allowed_chat_id:
            print("⚠️ Warning: TELEGRAM_CHAT_ID not configured in environment. Rejecting request for safety.")
            return False

        chat_id = str(update.effective_chat.id) if (update and update.effective_chat) else ""
        user_id = str(update.effective_user.id) if (update and update.effective_user) else ""

        allowed_ids = [cid.strip() for cid in allowed_chat_id.split(",") if cid.strip()]
        if chat_id in allowed_ids or user_id in allowed_ids:
            return True

        print(f"🚫 [Security] Blocked unauthorized bot command from Chat ID: {chat_id}, User ID: {user_id}")
        return False

    def admin_only(handler_func):
        """Decorator to enforce strict TELEGRAM_CHAT_ID authentication on Telegram commands."""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not is_authorized(update):
                await safe_reply(update, "⛔ Access Denied: You are not authorized to use this bot.")
                return
            return await handler_func(update, context, *args, **kwargs)
        return wrapper

    @admin_only
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

    @admin_only
    async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global should_stop
        should_stop = True
        await safe_reply(update, "Processing will stop after current task.")

    @admin_only
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
                err_str = str(e)
                log(f"Upload command error: {err_str}")
                if "YouTube token" in err_str or "re-authenticate" in err_str or "RefreshError" in err_str:
                    send_telegram_log(
                        "🚨 <b>YouTube Upload Failed: Authentication Expired</b>\n\n"
                        "Please re-authenticate your channel by running:\n"
                        "<code>/auth_youtube</code>"
                    )
            finally:
                global is_running
                is_running = False
                clear_progress_state()

        asyncio.get_event_loop().run_in_executor(None, run)

    @admin_only
    async def task_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _, _, _, active_flags = load_pipeline()
        lines = [f"{task.upper()}: {'🟢 ON' if state else '🔴 OFF'}" for task, state in active_flags.items()]
        await safe_reply(update, "⚙️ Current Task Status:\n" + "\n".join(lines))

    @admin_only
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

    @admin_only
    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _, _, get_upload_status, _ = load_pipeline()

        try:
            date_str = context.args[0] if context.args else datetime.now().strftime('%Y%m%d')
            status_text = get_upload_status(date_str)
            await safe_reply(update, status_text)
        except Exception as e:
            await safe_reply(update, f"Error fetching status: {e}")

    @admin_only
    async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now().strftime("%Y%m%d")
        log_path = f"logs/{today}.log"
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()[-4000:]
            await safe_reply(update, content)
        else:
            await safe_reply(update, "No logs found for today.")

    @admin_only
    async def auth_youtube_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from utils.youtube_utils import get_youtube_auth_url
            auth_url = get_youtube_auth_url(redirect_uri="http://localhost")
            msg = (
                "🔐 <b>YouTube Authorization</b>\n\n"
                "To connect or re-authenticate your YouTube channel:\n\n"
                f"1️⃣ <a href=\"{auth_url}\"><b>👉 Click Here to Authorize Google / YouTube 👈</b></a>\n\n"
                "2️⃣ Sign in to your Google account and click <b>Continue / Allow</b>.\n\n"
                "3️⃣ Your browser will redirect to a page starting with <code>http://localhost/?code=...</code> (it is normal if your browser says 'Cannot connect').\n\n"
                "4️⃣ Copy that redirected URL from your browser's address bar and reply here with:\n"
                "<code>/auth_code YOUR_REDIRECT_URL_OR_CODE</code>"
            )
            await safe_reply(update, msg, parse_mode="HTML")
        except Exception as e:
            await safe_reply(update, f"⚠️ Error generating authorization URL: {e}")

    @admin_only
    async def auth_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await safe_reply(update, "Usage:\n<code>/auth_code &lt;pasted_url_or_code&gt;</code>", parse_mode="HTML")
            return
        code_input = " ".join(context.args).strip()
        await safe_reply(update, "⏳ Verifying authentication with Google...")
        try:
            from utils.youtube_utils import finish_youtube_auth_flow
            channel_name = finish_youtube_auth_flow(code_input, redirect_uri="http://localhost")
            await safe_reply(
                update,
                f"🎉 <b>YouTube Authenticated Successfully!</b>\n\n"
                f"📺 Connected Channel: <b>{channel_name}</b>\n"
                f"🔑 New token saved to disk.\n"
                f"✨ Automated uploads are now active and ready.",
                parse_mode="HTML"
            )
        except Exception as e:
            await safe_reply(update, f"❌ Authentication failed: {e}\nPlease run /auth_youtube and try again.")

    @admin_only
    async def auth_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from utils.youtube_utils import get_youtube_auth_status
            status_data = get_youtube_auth_status()
            await safe_reply(update, status_data.get("message", "Unknown status"), parse_mode="HTML")
        except Exception as e:
            await safe_reply(update, f"Error checking auth status: {e}")

    @admin_only
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 <b>NarrateLoop Control Center</b>\n\n"
            "<b>🎬 Pipeline Controls:</b>\n"
            "• <code>/start</code> — Trigger full pipeline execution for today\n"
            "• <code>/upload [n]</code> — Upload specific story video (e.g. <code>/upload 1</code>, <code>/upload 2</code>, <code>/upload 3</code>)\n"
            "• <code>/stop</code> — Gracefully stop pipeline after current task\n\n"
            "<b>🔐 YouTube Authentication:</b>\n"
            "• <code>/auth_youtube</code> — Connect or re-authenticate your YouTube channel via 1-click Google OAuth link\n"
            "• <code>/auth_code [url_or_code]</code> — Complete OAuth verification by submitting the redirect URL or code\n"
            "• <code>/auth_status</code> — Check active YouTube connection status and connected channel name\n\n"
            "<b>📊 Status & Monitoring:</b>\n"
            "• <code>/status [YYYYMMDD]</code> — View rendered and uploaded video statuses for today or specific date\n"
            "• <code>/taskstatus</code> — View active/inactive status of individual pipeline stages\n"
            "• <code>/log</code> — View latest live pipeline execution logs\n"
            "• <code>/uptime</code> — Show system uptime and service duration\n\n"
            "<b>⚙️ Stage Flags Configuration:</b>\n"
            "• <code>/starttask [stage]</code> — Enable stage (<code>tts</code>, <code>subs</code>, <code>render</code>, <code>upload</code>)\n"
            "• <code>/stoptask [stage]</code> — Disable stage (<code>tts</code>, <code>subs</code>, <code>render</code>, <code>upload</code>)\n\n"
            "<b>ℹ️ General:</b>\n"
            "• <code>/help</code> — Show this comprehensive commands guide"
        )
        await safe_reply(update, msg, parse_mode="HTML")

    @admin_only
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
    app.add_handler(CommandHandler("auth_youtube", auth_youtube_command))
    app.add_handler(CommandHandler("auth_code", auth_code_command))
    app.add_handler(CommandHandler("auth_status", auth_status_command))
    app.add_handler(CommandHandler("starttask", lambda u, c: control_task(u, c, "start")))
    app.add_handler(CommandHandler("stoptask", lambda u, c: control_task(u, c, "stop")))

    def startup_run():
        try:
            send_startup_status("🚀 Initializing, please wait...", initial=True)
            log("Starting processing in background...", telegram=True)

            # Proactively check YouTube authentication health
            try:
                from utils.youtube_utils import get_youtube_auth_status
                auth_status_info = get_youtube_auth_status()
                if auth_status_info.get("status") in ["missing", "expired", "corrupt", "invalid"]:
                    send_telegram_log(
                        "⚠️ <b>YouTube Notice:</b> YouTube token is expired or not configured.\n"
                        "Send <code>/auth_youtube</code> to connect your channel for automated uploads."
                    )
            except Exception as ae:
                log(f"Warning during startup auth check: {ae}")

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

