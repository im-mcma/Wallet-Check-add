import os
import asyncio
import psutil
import aiohttp
from telegram import Bot
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn

# تنظیمات محیطی
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
INPUT_FILE = 'rich.txt'

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن یا چت آی‌دی تلگرام تنظیم نشده!")

class WalletChecker:
    def __init__(self, bot_token, chat_id):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.stats = {'total': 0, 'positive': 0, 'zero': 0, 'errors': 0}
        self._checking = False

    async def send_message(self, text):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            print(f"❌ خطا در ارسال پیام تلگرام: {e}")

    async def get_balance_blockstream(self, address):
        url = f"https://blockstream.info/api/address/{address}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    data = await resp.json()
                    return data.get("chain_stats", {}).get("funded_txo_sum", 0) - data.get("chain_stats", {}).get("spent_txo_sum", 0)
        except Exception as e:
            raise Exception(f"❗ خطا در دریافت موجودی: {str(e)}")

    async def check_address(self, address):
        try:
            balance_satoshi = await self.get_balance_blockstream(address)
            balance_btc = balance_satoshi / 1e8
            self.stats['total'] += 1
            if balance_btc > 0:
                self.stats['positive'] += 1
                text = f"✅ {address} | {balance_btc:.8f} BTC"
            else:
                self.stats['zero'] += 1
                text = f"⚠️ {address} | 0.00"
        except Exception as e:
            self.stats['errors'] += 1
            text = f"🚫 {address} | error: {str(e)[:40]}"
        await self.send_message(text)

    async def check_all_addresses(self):
        if self._checking:
            return "در حال بررسی هستیم"
        self._checking = True
        print("🚀 شروع بررسی آدرس‌ها")

        if not os.path.exists(INPUT_FILE):
            self._checking = False
            print(f"⚠️ فایل {INPUT_FILE} پیدا نشد!")
            return f"فایل {INPUT_FILE} پیدا نشد!"

        with open(INPUT_FILE, 'r') as f:
            addresses = [line.strip() for line in f if line.strip()]

        for addr in addresses:
            await self.check_address(addr)
            await asyncio.sleep(2)  # جلوگیری از محدودیت نرخ

        self._checking = False
        print("✅ بررسی آدرس‌ها کامل شد")
        return "✅ بررسی تمام آدرس‌ها کامل شد."

    async def periodic_report(self):
        print("📢 گزارش‌گیر دوره‌ای فعال شد.")
        while True:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            s = self.stats
            report = (
                f"📊 CPU: {cpu}% | RAM: {ram}%\n"
                f"🧮 بررسی شده: {s['total']}\n"
                f"✅ دارای موجودی: {s['positive']}\n"
                f"⚠️ بدون موجودی: {s['zero']}\n"
                f"🚫 خطاها: {s['errors']}"
            )
            await self.send_message(report)
            await asyncio.sleep(600)  # هر 10 دقیقه

checker = WalletChecker(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task1 = asyncio.create_task(checker.check_all_addresses())
    task2 = asyncio.create_task(checker.periodic_report())
    print("✅ تسک‌های بک‌گراند اجرا شدند.")
    try:
        yield
    finally:
        task1.cancel()
        task2.cancel()
        print("🛑 تسک‌ها لغو شدند.")

app = FastAPI(lifespan=lifespan)

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=1000)
