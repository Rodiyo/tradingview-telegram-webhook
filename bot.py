import os
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))

PENDING_FILE = "pending.json"
APPROVED_FILE = "approved.json"


def load_list(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r") as f:
        return json.load(f)


def save_list(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welkom bij T‑School alerts. Gebruik /register om je aan te melden.")


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
        if chat_id not in approved:
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


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    text = "Pending:\n"
    text += "\n".join(str(x) for x in pending) or "– geen –"
    text += "\n\nApproved:\n"
    text += "\n".join(str(x) for x in approved) or "– geen –"

    await update.message.reply_text(text)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("deny", deny))
    app.add_handler(CommandHandler("list", list_members))

    app.run_polling()


if __name__ == "__main__":
    main()

