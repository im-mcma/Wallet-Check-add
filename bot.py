import os
import time
import asyncio
import threading
from queue import Queue
from flask import Flask, jsonify
from tqdm import tqdm
from colorama import init, Fore
from bitcoinlib.services.services import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Bot
from telegram.error import RetryAfter, TelegramError

# رنگ‌ها برای خروجی ترمینال
init(autoreset=True)

# بیت‌کوین سرویس
service = Service()

# فایل ورودی
input_file = 'rich.txt'

# محیط تلگرام
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن ربات یا شناسه تلگرام تنظیم نشده‌اند!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# صف پیام و بافر گزارش‌های تجمیعی
message_queue = Queue()
batch_logs = []

# ارسال کننده async
async def send_to_telegram(text):
    sent = False
    while not sent:
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")
            sent = True
        except RetryAfter as e:
            wait_time = e.retry_after
            print(Fore.YELLOW + f"⚠️ توقف به‌خاطر محدودیت نرخ: {wait_time} ثانیه")
            await asyncio.sleep(wait_time)
        except TelegramError as e:
            print(Fore.RED + f"🚫 خطای تلگرام: {e}")
            await asyncio.sleep(5)

# مصرف‌کننده صف
def telegram_sender_worker():
    while True:
        text = message_queue.get()
        if text is None:
            break
        try:
            asyncio.run(send_to_telegram(text))
        except Exception as e:
            print(Fore.RED + f"❌ خطا در ارسال پیام: {e}")
        message_queue.task_done()

# ارسال هر ۱۰ دقیقه
def telegram_sender_batch():
    while True:
        time.sleep(600)  # هر ۱۰ دقیقه
        if batch_logs:
            text = "<b>📊 گزارش ۱۰ دقیقه اخیر:</b>\n\n" + "\n".join(batch_logs)
            try:
                asyncio.run(send_to_telegram(text))
            except Exception as e:
                print(Fore.RED + f"❌ خطا در ارسال تجمیعی: {e}")
            batch_logs.clear()

# افزودن پیام
def add_log(message: str):
    message_queue.put(message)
    batch_logs.append(message)

# بررسی آدرس‌ها
def check_addresses_and_report():
    checked_addresses = set()
    if not os.path.exists(input_file):
        print(Fore.RED + f'❌ فایل "{input_file}" پیدا نشد.')
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        addresses = [line.strip() for line in f if line.strip() and line.strip() not in checked_addresses]

    total = len(addresses)
    if total == 0:
        msg = "✅ هیچ آدرس جدیدی برای بررسی نیست."
        print(Fore.BLUE + msg)
        add_log(msg)
        return

    print(Fore.MAGENTA + f'\n📦 شروع بررسی {total} آدرس...\n' + '═' * 50)
    add_log(f'📦 شروع بررسی {total} آدرس...')

    def check_address(address):
        try:
            info = service.getbalance(address)
            balance = info['confirmed'] / 1e8
            if balance > 0:
                return ('rich', address, balance)
            else:
                return ('lose', address, balance)
        except Exception:
            return ('error', address, None)

    max_workers = min(20, total)

    with ThreadPoolExecutor(max_workers=max_workers) as executor, tqdm(total=total, unit="آدرس") as pbar:
        futures = {executor.submit(check_address, addr): addr for addr in addresses}

        for future in as_completed(futures):
            status, addr, bal = future.result()
            if status == 'rich':
                msg = f'✅ {addr} موجودی: {bal:.8f} BTC'
            elif status == 'lose':
                msg = f'⚠️ {addr} موجودی صفر'
            else:
                msg = f'🚫 {addr} خطا در بررسی'

            pbar.set_postfix_str(msg)
            pbar.update()
            add_log(msg)

    print('═' * 50)
    end_msg = f'🎯 پایان بررسی آدرس‌ها.'
    print(Fore.BLUE + end_msg)
    add_log('═' * 50)
    add_log(end_msg)

# روت وب
@app.route('/')
def index():
    return "<h2>🟢 اسکریپت بررسی آدرس فعال است</h2>"

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running"}), 200

# اجرای اصلی
if __name__ == '__main__':
    threading.Thread(target=check_addresses_and_report).start()
    threading.Thread(target=telegram_sender_worker, daemon=True).start()
    threading.Thread(target=telegram_sender_batch, daemon=True).start()
    app.run(host='0.0.0.0', port=1000)
