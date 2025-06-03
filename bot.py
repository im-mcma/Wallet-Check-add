import os
import time
import threading
import queue
from bitcoinlib.services.services import Service
from colorama import init, Fore
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests
from flask import Flask, jsonify

init(autoreset=True)

service = Service()

input_file = 'rich.txt'
output_file = 'results.txt'

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن ربات یا شناسه کانال تلگرام تنظیم نشده‌اند!")

app = Flask(__name__)

message_queue = queue.Queue()

def send_telegram_message(token, chat_id, text):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', '5'))
            print(Fore.YELLOW + f"⚠️ محدودیت نرخ تلگرام، توقف برای {retry_after} ثانیه")
            time.sleep(retry_after)
            return False
        return resp.status_code == 200
    except Exception as e:
        print(Fore.RED + f"خطا در ارسال پیام: {e}")
        return False

def telegram_sender_worker(token, chat_id):
    while True:
        text = message_queue.get()
        if text is None:
            break
        sent = False
        while not sent:
            sent = send_telegram_message(token, chat_id, text)
            if not sent:
                time.sleep(1)
        message_queue.task_done()

def enqueue_message(text):
    message_queue.put(text)

def add_log(message: str):
    enqueue_message(message)

def load_checked_addresses(file):
    checked = set()
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                if '|' in line:
                    checked.add(line.split('|')[0].strip())
                else:
                    checked.add(line.strip())
    return checked

@app.route('/')
def index():
    return "<h2>اسکریپت بررسی آدرس‌ها فعال است ✅</h2>"

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running"}), 200

def check_addresses_and_report():
    checked_addresses = load_checked_addresses(output_file)

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

    results = []

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

            results.append((status, addr, bal if bal is not None else 0))

            pbar.set_postfix_str(msg)
            pbar.update()

            add_log(msg)

    print('═' * 50)
    print(Fore.BLUE + f'🎯 پایان بررسی آدرس‌های جدید.')
    print(Fore.GREEN + f'✅ آدرس‌های دارای موجودی: {len([r for r in results if r[0]=="rich"])}')
    print(Fore.YELLOW + f'⚠️ آدرس‌های بدون موجودی: {len([r for r in results if r[0]=="lose"])}')
    print(Fore.RED + f'🚫 آدرس‌های خطا دار: {len([r for r in results if r[0]=="error"])}')

    add_log('═' * 50)
    add_log(f'🎯 پایان بررسی آدرس‌های جدید.')
    add_log(f'✅ آدرس‌های دارای موجودی: {len([r for r in results if r[0]=="rich"])}')
    add_log(f'⚠️ آدرس‌های بدون موجودی: {len([r for r in results if r[0]=="lose"])}')
    add_log(f'🚫 آدرس‌های خطا دار: {len([r for r in results if r[0]=="error"])}')

    with open(output_file, 'a', encoding='utf-8') as f_out:
        for status, addr, bal in results:
            if status == 'rich':
                f_out.write(f'{addr} | rich | {bal:.8f}\n')
            elif status == 'lose':
                f_out.write(f'{addr} | lose | {bal:.8f}\n')
            else:
                f_out.write(f'{addr} | error | error\n')

if __name__ == '__main__':
    threading.Thread(target=check_addresses_and_report).start()
    threading.Thread(target=telegram_sender_worker, args=(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), daemon=True).start()
    app.run(host='0.0.0.0', port=1000)
