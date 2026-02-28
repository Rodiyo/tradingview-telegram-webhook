import os
import psycopg2
from psycopg2.extras import RealDictCursor
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
from aiohttp import web
import threading

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")


# -------------------------
# TRADINGVIEW WEBHOOK SERVER
# -------------------------

async def handle_tradingview(request):
    try:
        data = await request.json()
    except:
        return web.Response(text="Invalid JSON", status=400)

    ticker = data.get("ticker")
    message = data.get("message", "")

    if not ticker:
        return web.Response(text="Missing ticker", status=400)

    cur.execute("SELECT chat_id FROM subscriptions WHERE symbol = %s", (ticker,))
    subscribers = [row["chat_id"] for row in cur.fetchall()]

    for chat_id in subscribers:
        try:
            await telegram_app.bot.send_message(
                chat_id,
                f"📈 Alert voor {ticker}:\n{message}"
            )
        except Exception as e:
            print(f"Failed to send message to {chat_id}: {e}")

    return web.Response(text="OK", status=200)


def start_webhook_server():
    app = web.Application()
    app.router.add_post("/webhook", handle_tradingview)
    web.run_app(app, port=8080)

# -------------------------
# DATABASE CONNECTIE
# -------------------------

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

# -------------------------
# TABELLEN AANMAKEN
# -------------------------

cur.execute("""
CREATE TABLE IF NOT EXISTS pending_users (
    chat_id BIGINT PRIMARY KEY,
    username TEXT
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS approved_users (
    chat_id BIGINT PRIMARY KEY,
    username TEXT
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tickers (
    symbol TEXT PRIMARY KEY
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id BIGINT,
    symbol TEXT,
    PRIMARY KEY (chat_id, symbol)
);
""")


# -------------------------
# HELPERS
# -------------------------

def get_username(update: Update):
    username = update.effective_user.username
    return username if username else "No username"


def is_approved(chat_id: int):
    cur.execute("SELECT 1 FROM approved_users WHERE chat_id = %s", (chat_id,))
    return cur.fetchone() is not None


# -------------------------
# COMMANDS
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
    "<b>Welcome to T‑School alerts.</b>\n"
    "Use /register to sign up.\n"
    "/subscriptions – Select which tickers you want to receive alerts for.",
    parse_mode="HTML"
)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = get_username(update)

    # Check approved
    cur.execute("SELECT 1 FROM approved_users WHERE chat_id = %s", (chat_id,))
    if cur.fetchone():
        return await update.message.reply_text("You are already approved for T‑School alerts.")

    # Check pending
    cur.execute("SELECT 1 FROM pending_users WHERE chat_id = %s", (chat_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO pending_users (chat_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (chat_id, username)
        )

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

    cur.execute("SELECT * FROM pending_users WHERE chat_id = %s", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("This user is not in the pending list.")

    cur.execute("DELETE FROM pending_users WHERE chat_id = %s", (chat_id,))
    cur.execute(
        "INSERT INTO approved_users (chat_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (chat_id, user["username"])
    )

    await update.message.reply_text(
        f"User {chat_id} (@{user['username']}) has been approved."
    )
    await context.bot.send_message(
        chat_id,
        "You have been approved for T‑School alerts!"
    )


async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /deny <chat_id>")

    chat_id = int(context.args[0])

    cur.execute("DELETE FROM pending_users WHERE chat_id = %s RETURNING username", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("This user is not in the pending list.")

    await update.message.reply_text(
        f"User {chat_id} (@{user['username']}) has been denied."
    )


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    cur.execute("SELECT * FROM pending_users")
    pending = cur.fetchall()

    cur.execute("SELECT * FROM approved_users")
    approved = cur.fetchall()

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
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /remove <chat_id>")

    chat_id = int(context.args[0])

    cur.execute("DELETE FROM approved_users WHERE chat_id = %s RETURNING username", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("This ID is not in the list.")

    await update.message.reply_text(
        f"Chat ID {chat_id} (@{user['username']}) has been removed."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    is_admin = (chat_id == ADMIN_CHAT_ID)

    text = (
        "<b>T‑School Alerts – Help</b>\n\n"
        "Available commands:\n"
        "/register – Request access to T‑School alerts\n"
        "/subscriptions – Select which tickers you want to receive alerts for\n"
        "/help – Show this help menu\n"
    )

    if is_admin:
        text += (
            "\n<b>Admin commands:</b>\n"
            "/addticker <symbol> – Add a new ticker\n"
            "/removeticker <symbol> – Remove a ticker\n"
            "/approve <chat_id> – Approve a pending user\n"
            "/deny <chat_id> – Deny a pending user\n"
            "/list – Show pending and approved users\n"
            "/remove <chat_id> – Remove an approved user\n"
        )

    await update.message.reply_text(text, parse_mode="HTML")


# -------------------------
# TICKERS
# -------------------------

async def add_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /addticker <symbol>")

    symbol = context.args[0].upper()

    cur.execute("INSERT INTO tickers (symbol) VALUES (%s) ON CONFLICT DO NOTHING", (symbol,))
    await update.message.reply_text(f"Ticker {symbol} added.")


async def remove_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /removeticker <symbol>")

    symbol = context.args[0].upper()

    cur.execute("DELETE FROM tickers WHERE symbol = %s RETURNING symbol", (symbol,))
    if not cur.fetchone():
        return await update.message.reply_text("Ticker not found.")

    await update.message.reply_text(f"Ticker {symbol} removed.")


# -------------------------
# SUBSCRIPTIONS
# -------------------------

async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not is_approved(chat_id):
        return await update.message.reply_text("You are not approved.")

    cur.execute("SELECT symbol FROM tickers")
    tickers = [row["symbol"] for row in cur.fetchall()]

    cur.execute("SELECT symbol FROM subscriptions WHERE chat_id = %s", (chat_id,))
    user_subs = [row["symbol"] for row in cur.fetchall()]

    keyboard = []
    row = []

    for t in tickers:
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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.from_user.id
    data = query.data

    if not data.startswith("toggle_"):
        return

    symbol = data.replace("toggle_", "")

    cur.execute(
        "SELECT 1 FROM subscriptions WHERE chat_id = %s AND symbol = %s",
        (chat_id, symbol)
    )
    exists = cur.fetchone()

    if exists:
        cur.execute(
            "DELETE FROM subscriptions WHERE chat_id = %s AND symbol = %s",
            (chat_id, symbol)
        )
        await query.edit_message_text(f"You unsubscribed from {symbol}.")
    else:
        cur.execute(
            "INSERT INTO subscriptions (chat_id, symbol) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (chat_id, symbol)
        )
        await query.edit_message_text(f"You subscribed to {symbol}.")


# -------------------------
# MAIN
# -------------------------

def main():
    global telegram_app
    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("register", register))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("deny", deny))
    telegram_app.add_handler(CommandHandler("list", list_members))
    telegram_app.add_handler(CommandHandler("remove", remove))
    telegram_app.add_handler(CommandHandler("help", help_command))

    telegram_app.add_handler(CommandHandler("addticker", add_ticker))
    telegram_app.add_handler(CommandHandler("removeticker", remove_ticker))
    telegram_app.add_handler(CommandHandler("subscriptions", subscriptions))

    telegram_app.add_handler(CallbackQueryHandler(handle_callback, pattern="^toggle_"))

    # Start Telegram polling in een thread
    threading.Thread(target=telegram_app.run_polling, daemon=True).start()

    # Start webhook server in de main thread (vereist door Railway)
    app = web.Application()
    app.router.add_post("/webhook", handle_tradingview)
    web.run_app(app, port=8080)




if __name__ == "__main__":
    main()
