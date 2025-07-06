import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import TimedOut

# Optional: Increase timeout for Telegram API calls
# from telegram.request import HTTPXRequest
# request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)

# Ensure main_pipeline can be imported
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

from main_pipeline import run_pipeline
from scripts.upload_pending import upload_pending_video  # your helper

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def safe_reply(update: Update, text: str):
    try:
        await update.message.reply_text(text)
    except TimedOut:
        print(f"[Telegram] Timed out while sending: {text}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "Starting full processing...")

    def task():
        run_pipeline()

    asyncio.get_event_loop().run_in_executor(None, task)

    await safe_reply(update, "Processing started  (Check logs for updates)")


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

    # app = ApplicationBuilder().token(TOKEN).request(request).build()  # Enable if using custom timeout
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload))

    print("Telegram bot running...")
    app.run_polling()
