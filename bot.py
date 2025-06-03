import os
import time
import threading
import psutil
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
    raise ValueError("Telegram bot token or chat ID not set!")

app = Flask(__name__)

message_queue = Queue()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

lock = threading.Lock()

# آمار کلی
stats = {
    'total': 0,
    'checked': 0,
    'rich': 0,
    'empty': 0,
    'error': 0,
}

def telegram_sender_worker():
    while True:
        messages = message_queue.get()
        if messages is None:
            break
        text = '\n'.join(messages)
        sent = False
        while not sent:
            try:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
                sent = True
            except RetryAfter as e:
                wait_time = e.retry_after
                print(Fore.YELLOW + f"⚠️ Telegram rate limit, sleeping for {wait_time} seconds")
                time.sleep(wait_time)
            except TelegramError as e:
                print(Fore.RED + f"Error sending message: {e}")
                time.sleep(5)
        message_queue.task_done()

def enqueue_messages_batch(lines, batch_size=20):
    batch = []
    for line in lines:
        batch.append(line)
        if len(batch) >= batch_size:
            message_queue.put(batch)
            batch = []
    if batch:
        message_queue.put(batch)

@app.route('/')
def index():
    return "<h2>Address checking script is running ✅</h2>"

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running"}), 200

def check_address(address):
    global stats
    try:
        info = service.getbalance(address)
        balance = info['confirmed'] / 1e8
        with lock:
            stats['checked'] += 1
            if balance > 0:
                stats['rich'] += 1
                return f'✅ {address} | {balance:.8f} BTC'
            else:
                stats['empty'] += 1
                return f'⚠️ {address} | 0.00'
    except Exception:
        with lock:
            stats['error'] += 1
        return f'🚫 {address} | error'

def check_addresses_and_report():
    global stats
    if not os.path.exists(input_file):
        print(Fore.RED + f'❌ Input file "{input_file}" not found.')
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        addresses = [line.strip() for line in f if line.strip()]

    stats['total'] = len(addresses)
    if stats['total'] == 0:
        print(Fore.BLUE + "✅ No new addresses to check.")
        message_queue.put(["✅ No new addresses to check."])
        return

    print(Fore.MAGENTA + f'\n📦 Starting check of {stats["total"]} addresses...\n' + '═' * 50)
    message_queue.put([f'📦 Starting check of {stats["total"]} addresses...'])

    max_workers = min(20, stats['total'])

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor, tqdm(total=stats['total'], unit="address") as pbar:
        futures = {executor.submit(check_address, addr): addr for addr in addresses}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            pbar.set_postfix_str(result)
            pbar.update()

            # هر 20 پیام رو ارسال می‌کنیم
            if len(results) >= 20:
                enqueue_messages_batch(results)
                results = []

    if results:
        enqueue_messages_batch(results)

    message_queue.put(['═' * 50, f'🎯 Finished checking addresses.'])

def periodic_report():
    while True:
        time.sleep(600)  # هر 10 دقیقه

        cpu_percent = psutil.cpu_percent(interval=1)
        ram_percent = psutil.virtual_memory().percent

        with lock:
            total = stats['total']
            checked = stats['checked']
            rich = stats['rich']
            empty = stats['empty']
            error = stats['error']

        progress_percent = (checked / total * 100) if total else 0

        report_lines = [
            f"📊 Summary Report (Every 10 minutes):",
            f"Total addresses: {total}",
            f"Checked: {checked}",
            f"Rich (BTC > 0): {rich}",
            f"Empty (0 BTC): {empty}",
            f"Errors: {error}",
            f"Progress: {progress_percent:.2f}%",
            f"CPU usage: {cpu_percent}%",
            f"RAM usage: {ram_percent}%",
        ]
        message_queue.put(report_lines)

if __name__ == '__main__':
    threading.Thread(target=check_addresses_and_report).start()
    threading.Thread(target=telegram_sender_worker, daemon=True).start()
    threading.Thread(target=periodic_report, daemon=True).start()
    app.run(host='0.0.0.0', port=1000)
