import os
import certifi

# Point the stdlib/OpenSSL trust store at certifi's CA bundle before any TLS
# client is constructed -- these are read at import time by libraries further
# down, so they must be set before those imports below, hence the unusual
# placement above them. This is the supported fix for the "certificate verify
# failed" errors seen on Windows, where there is no reliable system CA path;
# see start_telegram_bot() for why that matters more than it looks.
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["SSL_CERT_DIR"] = certifi.where()

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

from db.users.crud import get_or_create_user
from db.agents.crud import get_active_agents
from db.sessions.crud import switch_user_agent
from db.client import db
from core.router import MessageRouter

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(str(user.id), user.username or "Unknown")
    await update.message.reply_text(f"Hello {db_user.username}! Use /store to view available agents.")

async def store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    agents = await get_active_agents()
    if not agents:
        await update.message.reply_text("No active agents found in the store.")
        return
        
    keyboard = []
    for agent in agents:
        keyboard.append([InlineKeyboardButton(agent.name, callback_data=f"switch_{agent.id}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an agent:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("switch_"):
        agent_id = query.data.split("_")[1]
        user_id = str(query.from_user.id)
        
        db_user = await get_or_create_user(user_id, query.from_user.username or "Unknown")
        
        session = await switch_user_agent(db_user.id, agent_id)
        agent = await db.agent.find_unique(where={"id": agent_id})
        
        await query.edit_message_text(text=f"Switched to agent: {agent.name}\n{agent.description}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    response_text = await MessageRouter.process_telegram_message(
        telegram_id=user_id,
        username=update.effective_user.username,
        text=text
    )
    
    await update.message.reply_text(response_text)
    
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Voice messages are currently being upgraded to the new unified pipeline. Please send text for now.")

async def start_telegram_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env. Bot cannot start.")
        return
        
    from telegram.request import HTTPXRequest

    # This previously passed verify=False unconditionally, to get past SSL
    # failures on the original author's Windows machine. That flag does not
    # stay on a laptop: the same code path runs in production on Render, where
    # it disabled certificate verification for every Telegram API call --
    # including the ones carrying TELEGRAM_BOT_TOKEN -- leaving the bot open to
    # anyone able to intercept the connection and present their own cert.
    #
    # Pointing httpx at certifi's CA bundle is the actual fix for those Windows
    # failures (a missing/stale system trust store), so the escape hatch is not
    # needed in the common case. It is kept for genuinely broken local setups,
    # e.g. a corporate MITM proxy, but is now opt-in via env var and logs a
    # warning -- the old version failed open in silence, which is why it
    # survived all the way into a deployed service unnoticed.
    if os.getenv("TELEGRAM_INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        logger.warning(
            "TELEGRAM_INSECURE_SSL is set: TLS certificate verification is DISABLED. "
            "Never use this outside local development."
        )
        verify = False
    else:
        verify = certifi.where()

    request = HTTPXRequest(httpx_kwargs={"verify": verify})
    application = ApplicationBuilder().token(token).request(request).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("store", store))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logger.info("Telegram polling initialized.")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
