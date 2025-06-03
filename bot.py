import os
import asyncio
import psutil
from bitcoinlib.services.services import Service
from telegram import Bot
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# تنظیمات
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
INPUT_FILE = 'rich.txt'

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن یا چت آی‌دی تلگرام تنظیم نشده!")

service = Service()
app = FastAPI()

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
            print(f"خطا در ارسال پیام تلگرام: {e}")

    async def check_address(self, address):
        try:
            info = service.getbalance(address)
            balance = info['confirmed'] / 1e8
            self.stats['total'] += 1
            if balance > 0:
                self.stats['positive'] += 1
                text = f"✅ {address} | {balance:.8f} BTC"
            else:
                self.stats['zero'] += 1
                text = f"⚠️ {address} | 0.00"
        except Exception:
            self.stats['errors'] += 1
            text = f"🚫 {address} | error"
        await self.send_message(text)

    async def check_all_addresses(self):
        if self._checking:
            return "در حال حاضر در حال بررسی هستیم."
        self._checking = True

        if not os.path.exists(INPUT_FILE):
            self._checking = False
            return f"فایل {INPUT_FILE} پیدا نشد!"

        with open(INPUT_FILE, 'r') as f:
            addresses = [line.strip() for line in f if line.strip()]

        for addr in addresses:
            await self.check_address(addr)
            await asyncio.sleep(2)  # جلوگیری از Flood Control تلگرام

        self._checking = False
        return "✅ بررسی تمام آدرس‌ها کامل شد."

    async def periodic_report(self):
        while True:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            s = self.stats
            report = (
                f"📊 مصرف CPU: {cpu}% | RAM: {ram}%\n"
                f"🪙 تعداد بررسی شده: {s['total']}\n"
                f"✅ دارای موجودی: {s['positive']}\n"
                f"⚠️ بدون موجودی: {s['zero']}\n"
                f"🚫 خطاها: {s['errors']}"
            )
            await self.send_message(report)
            await asyncio.sleep(600)

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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(checker.check_all_addresses())   # ← شروع خودکار بررسی آدرس‌ها
    asyncio.create_task(checker.periodic_report())       # ← گزارش دوره‌ای

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=1000)
