import asyncio
import os
import logging
from telegram import Bot
from telegram.ext import ApplicationBuilder
from flask import Flask
from threading import Thread

# --- پیکربندی ---
TOKEN = os.environ.get("BOT_TOKEN") or "توکن_ربات"
CHANNEL_ID = os.environ.get("CHANNEL_ID") or "@channel_or_chat_id"
PORT = int(os.environ.get("PORT") or 1000)

# --- ساخت بات ---
application = ApplicationBuilder().token(TOKEN).build()
bot: Bot = application.bot

# --- صف پیام‌ها ---
send_queue = asyncio.Queue()

# --- کارگر ارسال پیام با rate limit ---
async def telegram_worker():
    while True:
        msgs = []
        try:
            for _ in range(30):  # حداکثر 30 پیام در batch
                msg = send_queue.get_nowait()
                msgs.append(msg)
        except asyncio.QueueEmpty:
            pass

        for msg in msgs:
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=msg)
                await asyncio.sleep(0.3)  # فاصله بین هر پیام
            except Exception as e:
                logging.warning(f"❌ خطا در ارسال پیام: {e}")

        await asyncio.sleep(3)  # فاصله بین batch ها

# --- افزودن پیام به صف ---
async def queue_message(msg):
    await send_queue.put(msg)

# --- بررسی آدرس‌ها (شبیه‌سازی‌شده) ---
async def address_scanner():
    count = 0
    while True:
        msg = f"📌 آدرس بررسی‌شده #{count}"
        await queue_message(msg)
        count += 1
        await asyncio.sleep(0.05)  # شبیه‌سازی پردازش

# --- Flask برای جلوگیری از sleep در Render ---
app = Flask(__name__)
@app.route("/")
def home():
    return "👀 Wallet Monitor Running"

@app.route("/stats")
def stats():
    return f"📊 در صف: {send_queue.qsize()} پیام"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# --- اجرای موازی همه تسک‌ها ---
async def main():
    asyncio.create_task(telegram_worker())
    asyncio.create_task(address_scanner())
    print("✅ تسک‌های بک‌گراند اجرا شدند.")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())
