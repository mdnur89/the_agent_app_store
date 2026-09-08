import asyncio
import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["SSL_CERT_DIR"] = certifi.where()

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)

load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Received start command!")
    await update.message.reply_text("Hello from standalone bot!")

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    # Was verify=False. Kept verifying here too: this scratch script is the
    # thing people copy when debugging the bot, so leaving the insecure flag
    # in it is how it grows back into transports/telegram/transport.py.
    request = HTTPXRequest(httpx_kwargs={"verify": certifi.where()})
    application = ApplicationBuilder().token(token).request(request).build()
    application.add_handler(CommandHandler("start", start))
    
    print("Starting polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Run forever
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
