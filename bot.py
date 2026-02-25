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


def get_username(update: Update):
    username = update.effective_user.username
    return username if username else "No username"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to T‑School alerts. Use /register to sign up."
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = get_username(update)

    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    # Convert old list format to new dict format if needed
    if isinstance(pending, list) and pending and isinstance(pending[0], int):
        pending = [{"chat_id": cid, "username": "Unknown"} for cid in pending]

    if isinstance(approved, list) and approved and isinstance(approved[0], int):
        approved = [{"chat_id": cid, "username": "Unknown"} for cid in approved]

    # Already approved
    if any(user["chat_id"] == chat_id for user in approved):
        await update.message.reply_text("You are already approved for T‑School alerts.")
        return

    # Add to pending if not already there
    if not any(user["chat_id"] == chat_id for user in pending):
        pending.append({"chat_id": chat_id, "username": username})
        save_list(PENDING_FILE, pending)

    await update.message.reply_text(
        "Your registration has been received. An admin will review your request."
    )

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"New registration received:\nChat ID: {chat_id}\nUsername: @{username}"
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /approve <chat_id>")
        return

    chat_id = int(context.args[0])

    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    # Find user in pending
    user = next((u for u in pending if u["chat_id"] == chat_id), None)

    if user:
        pending.remove(user)

        if not any(u["chat_id"] == chat_id for u in approved):
            approved.append(user)

        save_list(PENDING_FILE, pending)
        save_list(APPROVED_FILE, approved)

        await update.message.reply_text(
            f"User {chat_id} (@{user['username']}) has been approved."
        )
        await context.bot.send_message(
            chat_id,
            "You have been approved for T‑School alerts!"
        )
    else:
        await update.message.reply_text("This user is not in the pending list.")


async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /deny <chat_id>")
        return

    chat_id = int(context.args[0])
    pending = load_list(PENDING_FILE)

    user = next((u for u in pending if u["chat_id"] == chat_id), None)

    if user:
        pending.remove(user)
        save_list(PENDING_FILE, pending)
        await update.message.reply_text(
            f"User {chat_id} (@{user['username']}) has been denied."
        )
    else:
        await update.message.reply_text("This user is not in the pending list.")


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    pending = load_list(PENDING_FILE)
    approved = load_list(APPROVED_FILE)

    text = "Pending:\n"
    if pending:
        for u in pending:
            text += f"- {u['chat_id']} (@{u['username']})\n"
    else:
        text += "– none –\n"

    text += "\nApproved:\n"
    if approved:
        for u in approved:
            text += f"- {u['chat_id']} (@{u['username']})\n"
    else:
        text += "– none –"

    await update.message.reply_text(text)


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /remove <chat_id>")

    chat_id_to_remove = int(context.args[0])
    approved = load_list(APPROVED_FILE)

    user = next((u for u in approved if u["chat_id"] == chat_id_to_remove), None)

    if not user:
        return await update.message.reply_text("This ID is not in the list.")

    approved.remove(user)
    save_list(APPROVED_FILE, approved)

    await update.message.reply_text(
        f"Chat ID {chat_id_to_remove} (@{user['username']}) has been removed."
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("deny", deny))
    app.add_handler(CommandHandler("list", list_members))
    app.add_handler(CommandHandler("remove", remove))

    app.run_polling()


if __name__ == "__main__":
    main()
