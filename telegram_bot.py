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


async def safe_reply(update: Update, text: str):
    try:
        await update.message.reply_text(text)
    except TimedOut:
        print(f"[Telegram] Timed out while sending: {text}")


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


if __name__ == "__main__":
    if not TOKEN:
        print("Missing TELEGRAM_BOT_TOKEN in environment.")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload))

    print("Telegram bot running (Strict Admin Authentication Enabled)...")
    app.run_polling()
