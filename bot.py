import os
import asyncio
import psutil
from bitcoinlib.services.services import Service
from telegram import Bot
from telegram.error import RetryAfter, TelegramError
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# Config
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
INPUT_FILE = 'rich.txt'

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Telegram token or chat ID not set!")

service = Service()
app = FastAPI()

class WalletChecker:
    def __init__(self, bot_token, chat_id):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.queue = asyncio.Queue()
        self.stats = {
            'total': 0,
            'positive': 0,
            'zero': 0,
            'errors': 0
        }
        self._checking = False

    async def send_worker(self):
        while True:
            text = await self.queue.get()
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=text)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await self.queue.put(text)  # requeue for retry
            except TelegramError as e:
                print(f"Telegram Error: {e}")
            finally:
                self.queue.task_done()

    async def enqueue_message(self, msg):
        await self.queue.put(msg)

    async def check_address(self, address):
        try:
            info = service.getbalance(address)
            balance = info['confirmed'] / 1e8
            self.stats['total'] += 1
            if balance > 0:
                self.stats['positive'] += 1
                return f"✅ {address} | {balance:.8f} BTC"
            else:
                self.stats['zero'] += 1
                return f"⚠️ {address} | 0.00"
        except Exception:
            self.stats['errors'] += 1
            return f"🚫 {address} | error"

    async def check_all_addresses(self):
        if self._checking:
            return "Already checking"
        self._checking = True
        if not os.path.exists(INPUT_FILE):
            self._checking = False
            return f"Input file {INPUT_FILE} not found!"

        with open(INPUT_FILE, 'r') as f:
            addresses = [line.strip() for line in f if line.strip()]

        for addr in addresses:
            msg = await self.check_address(addr)
            await self.enqueue_message(msg)

        self._checking = False
        return "Check complete"

    async def periodic_report(self):
        while True:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            s = self.stats
            report = (
                f"📊 CPU: {cpu}% RAM: {ram}%\n"
                f"🪙 Checked: {s['total']}, Positive: {s['positive']}, "
                f"Zero: {s['zero']}, Errors: {s['errors']}"
            )
            await self.enqueue_message(report)
            await asyncio.sleep(600)  # 10 minutes

checker = WalletChecker(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

@app.get("/")
async def root():
    return {"status": "running", "message": "Wallet checker service is active."}

@app.get("/check")
async def manual_check():
    result = await checker.check_all_addresses()
    return JSONResponse({"message": result})

@app.get("/stats")
async def stats():
    return JSONResponse(checker.stats)

async def startup_event():
    asyncio.create_task(checker.send_worker())
    asyncio.create_task(checker.periodic_report())

app.add_event_handler("startup", startup_event)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=1000)
