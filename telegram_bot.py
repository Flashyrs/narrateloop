import os
import sys
import asyncio
from dotenv import load_dotenv
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

load_dotenv()

# Ensure main_pipeline can be imported
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

from main_pipeline import run_pipeline
from scripts.upload_pending import upload_pending_video

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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

    print(f"🚫 [Security] Blocked unauthorized bot request from Chat ID: {chat_id}, User ID: {user_id}")
    return False


def admin_only(handler_func):
    """Decorator to enforce strict TELEGRAM_CHAT_ID authentication on Telegram commands."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_authorized(update):
            await safe_reply(update, "⛔ Access Denied: You are not authorized to use this bot.")
            return
        return await handler_func(update, context, *args, **kwargs)
    return wrapper


async def safe_reply(update: Update, text: str, parse_mode: str = None):
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except TimedOut:
        print(f"[Telegram] Timed out while sending: {text}")
    except Exception as e:
        try:
            await update.message.reply_text(text)
        except Exception as e2:
            print(f"[Telegram] Failed sending reply: {e2}")


@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "Starting full processing...")

    def task():
        run_pipeline()

    asyncio.get_event_loop().run_in_executor(None, task)
    await safe_reply(update, "Processing started (Check logs for updates)")


@admin_only
async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "Uploading next video...")

    def task():
        return upload_pending_video()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, task)
    await safe_reply(update, result)


@admin_only
async def auth_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"✨ Automated uploads are now ready.",
            parse_mode="HTML"
        )
    except Exception as e:
        await safe_reply(update, f"❌ Authentication failed: {e}\nPlease run /auth_youtube and try again.")


@admin_only
async def auth_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from utils.youtube_utils import get_youtube_auth_status
        status_data = get_youtube_auth_status()
        await safe_reply(update, status_data.get("message", "Unknown status"), parse_mode="HTML")
    except Exception as e:
        await safe_reply(update, f"Error checking auth status: {e}")


if __name__ == "__main__":
    if not TOKEN:
        print("Missing TELEGRAM_BOT_TOKEN in environment.")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("auth_youtube", auth_youtube))
    app.add_handler(CommandHandler("auth_code", auth_code))
    app.add_handler(CommandHandler("auth_status", auth_status))

    print("Telegram bot running (Strict Admin Authentication Enabled)...")
    app.run_polling()
