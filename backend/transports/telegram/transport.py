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
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

from db.users.crud import get_or_create_user
from db.agents.crud import get_visible_agent, list_visible_agents
from db.sessions.crud import get_active_session, switch_user_agent
from db.client import db
from core.router import MessageRouter
from services.tts.service import VoiceUnavailable, synthesize, transcribe

logger = logging.getLogger(__name__)
_link_attempts: dict[str, deque[float]] = defaultdict(deque)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(str(user.id), user.username or "Unknown")
    await update.message.reply_text(f"Hello {db_user.username}! Use /store to view available agents.")

async def store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    db_user = await get_or_create_user(str(telegram_user.id), telegram_user.username or "Unknown")
    agents = await list_visible_agents(db_user.id if db_user.supabase_user_id else None, active_only=True)
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
        agent_id = query.data.split("_", 1)[1]
        user_id = str(query.from_user.id)
        
        db_user = await get_or_create_user(user_id, query.from_user.username or "Unknown")
        
        agent = await get_visible_agent(agent_id, db_user.id if db_user.supabase_user_id else None)
        if not agent or not agent.isActive:
            await query.edit_message_text(text="That agent is unavailable.")
            return
        session = await switch_user_agent(db_user.id, agent_id)
        
        await query.edit_message_text(text=f"Switched to agent: {agent.name}\n{agent.description}")


def _link_rate_limited(chat_id: str) -> bool:
    """In-process throttle; use Redis before running multiple bot workers."""
    now = time.monotonic()
    attempts = _link_attempts[chat_id]
    while attempts and now - attempts[0] > 60:
        attempts.popleft()
    if len(attempts) >= 5:
        return True
    attempts.append(now)
    return False


async def link_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    if _link_rate_limited(chat_id):
        await update.message.reply_text("Too many link attempts. Try again in a minute.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Use /link CODE with the 8-character code from Settings.")
        return
    code = context.args[0].strip().upper()
    try:
        async with db.tx() as transaction:
            link = await transaction.telegramlinkcode.find_unique(where={"code": code})
            expiry = link.expires_at if link else None
            now = datetime.now(timezone.utc)
            if expiry and expiry.tzinfo is None:
                now = now.replace(tzinfo=None)
            if not link or link.used_at is not None or expiry <= now:
                raise ValueError("That link code is invalid, expired, or already used.")
            burned = await transaction.telegramlinkcode.update_many(
                where={"id": link.id, "used_at": None}, data={"used_at": datetime.now(timezone.utc)}
            )
            if burned != 1:
                raise ValueError("That link code was already used.")
            target = await transaction.user.find_unique(where={"id": link.user_id})
            existing = await transaction.user.find_unique(where={"telegram_id": chat_id})
            if not target:
                raise ValueError("The account for this code no longer exists.")
            if existing and existing.id != target.id:
                if existing.supabase_user_id:
                    raise ValueError("This Telegram account is already linked to another web account.")
                await transaction.session.update_many(where={"user_id": existing.id}, data={"user_id": target.id})
                await transaction.agent.update_many(where={"owner_id": existing.id}, data={"owner_id": target.id})
                await transaction.user.delete(where={"id": existing.id})
            await transaction.user.update(
                where={"id": target.id},
                data={"telegram_id": chat_id, "username": update.effective_user.username or target.username},
            )
        await update.message.reply_text("Telegram is now linked to your Hub account.")
    except ValueError as exc:
        await update.message.reply_text(str(exc))
    except Exception:
        logger.exception("Telegram account linking failed")
        await update.message.reply_text("Linking failed. Please generate a new code and try again.")

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
    """Voice note in, spoken reply out.

    Mirrors the user's modality: someone who sent audio gets audio back. The
    transcript is echoed first for two reasons -- it shows what the agent
    actually heard (so a misrecognition is obvious rather than baffling), and
    it leaves a readable record in a chat history that is otherwise unsearchable
    audio blobs.
    """
    user = update.effective_user
    try:
        voice = update.message.voice or update.message.audio
        audio_file = await context.bot.get_file(voice.file_id)
        audio = bytes(await audio_file.download_as_bytearray())
        transcript = await transcribe(audio, filename="voice.ogg")
    except VoiceUnavailable as exc:
        await update.message.reply_text(f"🎤 {exc}\n\nSend your message as text and I'll pick it up from there.")
        return
    except Exception:
        logger.exception("Could not read Telegram voice note")
        await update.message.reply_text("I couldn't read that voice note. Please try again, or send text.")
        return

    await update.message.reply_text(f'🎤 _I heard:_ "{transcript}"', parse_mode="Markdown")

    reply = await MessageRouter.process_telegram_message(
        telegram_id=str(user.id), username=user.username, text=transcript,
    )
    await update.message.reply_text(reply)

    # Speech is best-effort on top of a reply the user already has. A TTS
    # outage must not swallow the answer, so failure here is logged and
    # nothing more -- the text above is the deliverable.
    try:
        session = await get_active_session(user_id=(await get_or_create_user(str(user.id), user.username or "Unknown")).id)
        voice_type = session.agent.voice_type if session and session.agent else None
        await update.message.reply_voice(voice=await synthesize(reply, voice_type))
    except VoiceUnavailable as exc:
        logger.info("Skipping spoken reply: %s", exc)
    except Exception:
        logger.exception("Could not send spoken reply")

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
    application.add_handler(CommandHandler("link", link_telegram))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # AUDIO as well as VOICE: a forwarded music-style clip or a file recorded
    # outside Telegram arrives as AUDIO, and handle_voice reads both.
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    logger.info("Telegram polling initialized.")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
