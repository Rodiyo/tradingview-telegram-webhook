import os
import json
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))

PENDING_FILE = "pending.json"
APPROVED_FILE = "approved.json"
TICKERS_FILE = "tickers.json"
SUBSCRIPTIONS_FILE = "subscriptions.json"


# -------------------------
# JSON HELPERS
# -------------------------

def load_json(filename, default):
    if not os.path.exists(filename):
        return default
    with open(filename, "r") as f:
        return json.load(f)


def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)


# -------------------------
# USERNAME HELPER
# -------------------------

def get_username(update: Update):
    username = update.effective_user.username
    return username if username else "No username"


# -------------------------
# BASIC COMMANDS
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to T‑School alerts. Use /register to sign up."
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = get_username(update)

    pending = load_json(PENDING_FILE, [])
    approved = load_json(APPROVED_FILE, [])

    # Convert old list format to new dict format if needed
    if pending and isinstance(pending[0], int):
        pending = [{"chat_id": cid, "username": "Unknown"} for cid in pending]

    if approved and isinstance(approved[0], int):
        approved = [{"chat_id": cid, "username": "Unknown"} for cid in approved]

    # Already approved
    if any(u["chat_id"] == chat_id for u in approved):
        await update.message.reply_text("You are already approved for T‑School alerts.")
        return

    # Add to pending
    if not any(u["chat_id"] == chat_id for u in pending):
        pending.append({"chat_id": chat_id, "username": username})
        save_json(PENDING_FILE, pending)

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
        return await update.message.reply_text("Usage: /approve <chat_id>")

    chat_id = int(context.args[0])
    pending = load_json(PENDING_FILE, [])
    approved = load_json(APPROVED_FILE, [])

    user = next((u for u in pending if u["chat_id"] == chat_id), None)

    if user:
        pending.remove(user)
        if not any(u["chat_id"] == chat_id for u in approved):
            approved.append(user)

        save_json(PENDING_FILE, pending)
        save_json(APPROVED_FILE, approved)

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
        return await update.message.reply_text("Usage: /deny <chat_id>")

    chat_id = int(context.args[0])
    pending = load_json(PENDING_FILE, [])

    user = next((u for u in pending if u["chat_id"] == chat_id), None)

    if user:
        pending.remove(user)
        save_json(PENDING_FILE, pending)
        await update.message.reply_text(
            f"User {chat_id} (@{user['username']}) has been denied."
        )
    else:
        await update.message.reply_text("This user is not in the pending list.")


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    pending = load_json(PENDING_FILE, [])
    approved = load_json(APPROVED_FILE, [])

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

    chat_id = int(context.args[0])
    approved = load_json(APPROVED_FILE, [])

    user = next((u for u in approved if u["chat_id"] == chat_id), None)

    if not user:
        return await update.message.reply_text("This ID is not in the list.")

    approved.remove(user)
    save_json(APPROVED_FILE, approved)

    await update.message.reply_text(
        f"Chat ID {chat_id} (@{user['username']}) has been removed."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    is_admin = (chat_id == ADMIN_CHAT_ID)

    text = (
        "<b>T‑School Alerts – Help</b><br><br>"
        "Available commands:<br>"
        "/register – Request access to T‑School alerts<br>"
        "/subscriptions – Select which tickers you want to receive alerts for<br>"
        "/help – Show this help menu<br><br>"
    )

    if is_admin:
        text += (
            "<b>Admin commands:</b><br>"
            "/addticker &lt;symbol&gt; – Add a new ticker<br>"
            "/removeticker &lt;symbol&gt; – Remove a ticker<br>"
            "/approve &lt;chat_id&gt; – Approve a pending user<br>"
            "/deny &lt;chat_id&gt; – Deny a pending user<br>"
            "/list – Show pending and approved users<br>"
            "/remove &lt;chat_id&gt; – Remove an approved user<br>"
        )

    await update.message.reply_text(text, parse_mode="HTML")



# -------------------------
# TICKER ADMIN COMMANDS
# -------------------------

async def add_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /addticker <symbol>")

    symbol = context.args[0].upper()
    tickers = load_json(TICKERS_FILE, [])

    if symbol in tickers:
        return await update.message.reply_text("Ticker already exists.")

    tickers.append(symbol)
    save_json(TICKERS_FILE, tickers)

    await update.message.reply_text(f"Ticker {symbol} added.")


async def remove_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /removeticker <symbol>")

    symbol = context.args[0].upper()
    tickers = load_json(TICKERS_FILE, [])

    if symbol not in tickers:
        return await update.message.reply_text("Ticker not found.")

    tickers.remove(symbol)
    save_json(TICKERS_FILE, tickers)

    await update.message.reply_text(f"Ticker {symbol} removed.")


# -------------------------
# USER SUBSCRIPTIONS MENU
# -------------------------

async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    approved = load_json(APPROVED_FILE, [])

    if not any(u["chat_id"] == chat_id for u in approved):
        return await update.message.reply_text("You are not approved.")

    tickers = load_json(TICKERS_FILE, [])
    subs = load_json(SUBSCRIPTIONS_FILE, {})

    user_subs = subs.get(str(chat_id), [])

    keyboard = []
    row = []

    for i, t in enumerate(tickers):
        label = f"✓ {t}" if t in user_subs else t
        row.append(InlineKeyboardButton(label, callback_data=f"toggle_{t}"))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    await update.message.reply_text(
        "Select the tickers you want to receive:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -------------------------
# CALLBACK HANDLER
# -------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.from_user.id
    data = query.data

    if not data.startswith("toggle_"):
        return

    ticker = data.replace("toggle_", "")
    subs = load_json(SUBSCRIPTIONS_FILE, {})
    user_subs = subs.get(str(chat_id), [])

    if ticker in user_subs:
        user_subs.remove(ticker)
        await query.edit_message_text(f"You unsubscribed from {ticker}.")
    else:
        user_subs.append(ticker)
        await query.edit_message_text(f"You subscribed to {ticker}.")

    subs[str(chat_id)] = user_subs
    save_json(SUBSCRIPTIONS_FILE, subs)


# -------------------------
# MAIN
# -------------------------

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("deny", deny))
    app.add_handler(CommandHandler("list", list_members))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("help", help_command))
    
    # NEW TICKER COMMANDS
    app.add_handler(CommandHandler("addticker", add_ticker))
    app.add_handler(CommandHandler("removeticker", remove_ticker))
    app.add_handler(CommandHandler("subscriptions", subscriptions))

    # CALLBACK HANDLER
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
