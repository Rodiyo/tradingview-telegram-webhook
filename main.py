import os
import json
import requests
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# -----------------------------
# CONFIG
# -----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))  # Jouw eigen chat ID

PENDING_FILE = "pending.json"
APPROVED_FILE = "approved.json"

app = FastAPI()

# -----------------------------
# HELPERS
# -----------------------------
def load_list(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r") as f:
        return json.load(f)

def save_list(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

# -----------------------------
# BOT COMMANDS
# -----------------------------
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    if chat_id in approved:
        await update.message.reply_text("Je bent al goedgekeurd voor T‑School alerts.")
        return

    if chat_id not in pending:
        pending.append(chat_id)
        save_list(PENDING_FILE, pending)

    await update.message.reply_text("Je registratie is ontvangen. Een admin zal je aanvraag beoordelen.")

    # Meld aan admin
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"Nieuwe registratie ontvangen:\nChat ID: {chat_id}"
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("Gebruik: /approve <chat_id>")
        return

    chat_id = int(context.args[0])
    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    if chat_id in pending:
        pending.remove(chat_id)
        approved.append(chat_id)
        save_list(PENDING_FILE, pending)
        save_list(APPROVED_FILE, approved)

        await update.message.reply_text(f"Gebruiker {chat_id} is goedgekeurd.")
        await context.bot.send_message(chat_id, "Je bent goedgekeurd voor T‑School alerts!")
    else:
        await update.message.reply_text("Deze gebruiker staat niet in de pending lijst.")

async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("Gebruik: /deny <chat_id>")
        return

    chat_id = int(context.args[0])
    pending = load_list(PENDING_FILE)

    if chat_id in pending:
        pending.remove(chat_id)
        save_list(PENDING_FILE, pending)
        await update.message.reply_text(f"Gebruiker {chat_id} is geweigerd.")
    else:
        await update.message.reply_text("Deze gebruiker staat niet in de pending lijst.")

# -----------------------------
# BROADCAST FUNCTION
# -----------------------------
async def broadcast_alert(bot, message):
    approved = load_list(APPROVED_FILE)
    for user in approved:
        try:
            await bot.send_message(user, message)
        except:
            pass  # gebruiker blokkeerde bot of fout → negeren

# -----------------------------
# FASTAPI ROUTES
# -----------------------------
@app.get("/")
def home():
    return {"status": "running"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", str(data))

    # Stuur naar admin (optioneel)
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": ADMIN_CHAT_ID, "text": message}
    )

    # Broadcast naar members
    await broadcast_alert(app.bot, message)

    return {"status": "sent"}

# -----------------------------
# START TELEGRAM BOT
# -----------------------------
async def start_bot():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("deny", deny))

    app.bot = application.bot  # nodig voor webhook broadcast

    await application.initialize()
    await application.start()
    print("Telegram bot is gestart.")

import asyncio
asyncio.create_task(start_bot())
