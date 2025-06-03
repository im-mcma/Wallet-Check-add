import os
import time
import threading
from bitcoinlib.services.services import Service
from colorama import init, Fore
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from flask import Flask, jsonify
from queue import Queue
from telegram import Bot
from telegram.error import RetryAfter, TelegramError

init(autoreset=True)

service = Service()

input_file = 'rich.txt'

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن ربات یا شناسه کانال تلگرام تنظیم نشده‌اند!")

app = Flask(__name__)

message_queue = Queue()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

def telegram_sender_worker():
    while True:
        text = message_queue.get()
        if text is None:
            break
        sent = False
        while not sent:
            try:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
                sent = True
            except RetryAfter as e:
                wait_time = e.retry_after
                print(Fore.YELLOW + f"⚠️ محدودیت نرخ تلگرام، توقف برای {wait_time} ثانیه")
                time.sleep(wait_time)
            except TelegramError as e:
                print(Fore.RED + f"خطا در ارسال پیام: {e}")
                time.sleep(5)
        message_queue.task_done()

def enqueue_message(text):
    message_queue.put(text)

def add_log(message: str):
    enqueue_message(message)

def load_checked_addresses(file):
    checked = set()
    # چون قبلا دیگه خروجی نداریم، می‌تونیم فایل رو نگیریم، اما اگر خواستی می‌تونی آدرس‌های ورودی رو چک کنی تا تکراری نزنیم
    # در اینجا برای سادگی، فقط فایل ورودی رو چک می‌کنیم که آدرس‌ها تکراری نباشن
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                checked.add(line.strip())
    return checked

@app.route('/')
def index():
    return "<h2>اسکریپت بررسی آدرس‌ها فعال است ✅</h2>"

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running"}), 200

def check_addresses_and_report():
    # فقط بارگذاری آدرس‌های ورودی که تکراری نباشند
    checked_addresses = set()

    if not os.path.exists(input_file):
        print(Fore.RED + f'❌ فایل ورودی "{input_file}" پیدا نشد.')
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        addresses = [line.strip() for line in f if line.strip() and line.strip() not in checked_addresses]

    total = len(addresses)
    if total == 0:
        print(Fore.BLUE + "✅ هیچ آدرس جدیدی برای بررسی وجود ندارد.")
        add_log("✅ هیچ آدرس جدیدی برای بررسی وجود ندارد.")
        return

    print(Fore.MAGENTA + f'\n📦 شروع بررسی {total} آدرس جدید...\n' + '═' * 50)
    add_log(f'📦 شروع بررسی {total} آدرس جدید...')

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
    print(Fore.BLUE + f'🎯 پایان بررسی آدرس‌های جدید.')
    add_log('═' * 50)
    add_log(f'🎯 پایان بررسی آدرس‌های جدید.')

if __name__ == '__main__':
    threading.Thread(target=check_addresses_and_report).start()
    threading.Thread(target=telegram_sender_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=1000)
