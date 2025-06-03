import os
import json
import time
import random
import logging
import threading
from bit import Key
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from flask import Flask

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")  # e.g., "@your_channel"

bot = Bot(token=TOKEN)

app = Flask(__name__)
log_queue = []

# Read addresses from file
with open("add.txt", "r") as f:
    TARGET_ADDRESSES = set(line.strip() for line in f if line.strip())

def check_wallets():
    logging.info(f"🎯 Scanning {len(TARGET_ADDRESSES)} target addresses...")
    while True:
        key = Key()
        address = key.address
        private_key = key.to_wif()
        if address in TARGET_ADDRESSES:
            log = {
                "match": True,
                "address": address,
                "private_key": private_key,
                "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            log_queue.append(log)
        time.sleep(0.01)  # adjust for CPU

def send_logs_periodically():
    while True:
        if log_queue:
            messages = []
            while log_queue:
                log = log_queue.pop(0)
                messages.append(log)

            for log in messages:
                send_match_log(log)
        time.sleep(600)  # every 10 minutes

def send_match_log(log):
    text = (
        f"🚨 <b>Match Found!</b>\n\n"
        f"🔐 <b>Private Key:</b> <code>{log['private_key']}</code>\n"
        f"📮 <b>Address:</b> <code>{log['address']}</code>\n"
        f"🕒 <b>Time:</b> {log['time']}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 View on Blockchain", url=f"https://www.blockchain.com/btc/address/{log['address']}")],
        [InlineKeyboardButton("📋 Copy Private Key", callback_data=f"copy:{log['private_key']}")]
    ])

    bot.send_message(
        chat_id=CHANNEL_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@app.route("/", methods=["GET", "HEAD"])
def home():
    return "✅ Wallet Checker Running"

if __name__ == "__main__":
    threading.Thread(target=check_wallets).start()
    threading.Thread(target=send_logs_periodically).start()
    app.run(host="0.0.0.0", port=1000)
