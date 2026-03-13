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
import asyncio
from datetime import datetime, timedelta

# -------------------------
# CONFIG
# -------------------------

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

WHIPSAW_WINDOW_MINUTES = 10
COOLDOWN_MINUTES = 10

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

cur.execute("""
CREATE TABLE IF NOT EXISTS last_signals (
    symbol TEXT PRIMARY KEY,
    last_signal TEXT
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS signal_state (
    symbol TEXT PRIMARY KEY,
    signal_1 TEXT,
    time_1 TIMESTAMP,
    signal_2 TEXT,
    time_2 TIMESTAMP,
    signal_3 TEXT,
    time_3 TIMESTAMP,
    signal_4 TEXT,
    time_4 TIMESTAMP,
    cooldown_until TIMESTAMP
);
""")
# -------------------------
# TRADINGVIEW WEBHOOK HANDLER
# -------------------------

import json

async def handle_tradingview(request):
    try:
        # Probeer echte JSON
        data = await request.json()
    except:
        # Fallback: TradingView stuurt vaak text/plain
        try:
            raw = await request.text()
            data = json.loads(raw)
        except:
            return web.Response(text="Invalid JSON", status=400)


    # -----------------------------------------
    # 1. TELEGRAM UPDATE? (webhook passthrough)
    # -----------------------------------------
    if isinstance(data, dict) and (
        "update_id" in data or
        isinstance(data.get("message"), dict) or
        "callback_query" in data
    ):
        try:
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.update_queue.put(update)
            return web.Response(text="OK", status=200)
        except:
            return web.Response(text="Telegram error", status=500)

    # -----------------------------------------
    # 2. TRADINGVIEW ALERT
    # -----------------------------------------
    ticker = data.get("ticker")
    message = data.get("message", "")

    if not ticker:
        return web.Response(text="Missing ticker", status=400)

    now = datetime.utcnow()

    # -----------------------------------------
    # 3. STATE OPHALEN
    # -----------------------------------------
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT signal_1, time_1,
                       signal_2, time_2,
                       signal_3, time_3,
                       signal_4, time_4,
                       cooldown_until
                FROM signal_state
                WHERE symbol = %s
            """, (ticker,))
            row = cur.fetchone()

            if not row:
                row = {
                    "signal_1": None, "time_1": None,
                    "signal_2": None, "time_2": None,
                    "signal_3": None, "time_3": None,
                    "signal_4": None, "time_4": None,
                    "cooldown_until": None
                }

            s1, t1 = row["signal_1"], row["time_1"]
            s2, t2 = row["signal_2"], row["time_2"]
            s3, t3 = row["signal_3"], row["time_3"]
            s4, t4 = row["signal_4"], row["time_4"]
            cooldown_until = row["cooldown_until"]

    except Exception as e:
        print("State read error:", e)
        return web.Response(text="State error", status=500)

    # -----------------------------------------
    # 4. ACTIEVE COOLDOWN?
    # -----------------------------------------
    if cooldown_until and now < cooldown_until:
        print(f"[{ticker}] Cooldown actief tot {cooldown_until}, signaal genegeerd.")
        return web.Response(text="Cooldown active", status=200)

    # -----------------------------------------
    # 5. DUPLICATE FILTER
    # -----------------------------------------
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT last_signal FROM last_signals WHERE symbol = %s", (ticker,))
            row_dup = cur.fetchone()

            if row_dup and row_dup["last_signal"] == message:
                print(f"[{ticker}] Duplicate signaal ({message}), genegeerd.")
                return web.Response(text="Duplicate ignored", status=200)

            cur.execute("""
                INSERT INTO last_signals (symbol, last_signal)
                VALUES (%s, %s)
                ON CONFLICT (symbol) DO UPDATE SET last_signal = EXCLUDED.last_signal
            """, (ticker, message))

    except Exception as e:
        print("Duplicate check error:", e)
        return web.Response(text="Duplicate error", status=500)

    # -----------------------------------------
    # 6. WHIPSAW DETECTIE (A-B-A-B)
    # -----------------------------------------
    whipsaw_detected = False

    if s4 and s3 and s2:
        # patroon: s4=A, s3=B, s2=A, new=B
        if s4 == s2 and s3 != s4 and message == s3:
            if t4 and (now - t4) < timedelta(minutes=WHIPSAW_WINDOW_MINUTES):
                whipsaw_detected = True
                print(f"[{ticker}] WHIPSAW A-B-A-B gedetecteerd.")

    # -----------------------------------------
    # 7. RESET BIJ C
    # -----------------------------------------
    if s4 and s3:
        A = s4
        B = s3
        if message != A and message != B:
            print(f"[{ticker}] Nieuw signaal C → volledige reset.")
            s1 = s2 = s3 = s4 = None
            t1 = t2 = t3 = t4 = None
            cooldown_until = None

    # -----------------------------------------
    # 8. NIEUWE STATE SCHUIVEN
    # -----------------------------------------
    s4, t4 = s3, t3
    s3, t3 = s2, t2
    s2, t2 = s1, t1
    s1, t1 = message, now

    # -----------------------------------------
    # 9. COOLDOWN ACTIVEREN (maar signaal nog versturen)
    # -----------------------------------------
    if whipsaw_detected:
        cooldown_until = now + timedelta(minutes=COOLDOWN_MINUTES)
        print(f"[{ticker}] Cooldown geactiveerd tot {cooldown_until}")

    # -----------------------------------------
    # 10. STATE OPSLAAN
    # -----------------------------------------
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO signal_state (
                    symbol,
                    signal_1, time_1,
                    signal_2, time_2,
                    signal_3, time_3,
                    signal_4, time_4,
                    cooldown_until
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (symbol) DO UPDATE SET
                    signal_1 = EXCLUDED.signal_1,
                    time_1 = EXCLUDED.time_1,
                    signal_2 = EXCLUDED.signal_2,
                    time_2 = EXCLUDED.time_2,
                    signal_3 = EXCLUDED.signal_3,
                    time_3 = EXCLUDED.time_3,
                    signal_4 = EXCLUDED.signal_4,
                    time_4 = EXCLUDED.time_4,
                    cooldown_until = EXCLUDED.cooldown_until
            """, (
                ticker,
                s1, t1,
                s2, t2,
                s3, t3,
                s4, t4,
                cooldown_until
            ))
    except Exception as e:
        print("State save error:", e)
        return web.Response(text="State save error", status=500)

    # -----------------------------------------
    # 11. SUBSCRIBERS OPHALEN
    # -----------------------------------------
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT chat_id FROM subscriptions WHERE symbol = %s", (ticker,))
            subscribers = [row["chat_id"] for row in cur.fetchall()]
    except Exception as e:
        print("Subscription read error:", e)
        return web.Response(text="Database error", status=500)

    # -----------------------------------------
    # 12. ALERT VERSTUREN
    # -----------------------------------------
    for chat_id in subscribers:
        try:
            direction = data.get("direction")
            entry = data.get("entry_price")
            stop = data.get("stoploss_price")

            skip_fields = (
                message.startswith("New BOX") or
                message.startswith("Crossing") or
                message.startswith("Real Exit") or
                message.startswith("Real Long") or
                message.startswith("Real Short")
            )

            if skip_fields:
                text = f"📈 Alert voor {ticker}:\n{message}"
            else:
                text = (
                    f"📈 Alert voor {ticker}:\n"
                    f"{message}\n\n"
                    f"Direction: {direction}\n"
                    f"Entry: {entry}\n"
                    f"Stoploss: {stop}\n"
                )

            await telegram_app.bot.send_message(chat_id, text)

        except Exception as e:
            print(f"Send error to {chat_id}:", e)

    return web.Response(text="OK", status=200)


# -------------------------
# HELPERS
# -------------------------

def get_username(update: Update):
    username = update.effective_user.username
    return username if username else "NoUsername"

def is_approved(chat_id: int):
    cur.execute("SELECT 1 FROM approved_users WHERE chat_id = %s", (chat_id,))
    return cur.fetchone() is not None

# -------------------------
# COMMANDS
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Welcome to T‑School alerts.</b>\n"
        "Use /register to request access.\n"
        "Use /subscriptions to manage your tickers.",
        parse_mode="HTML"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = get_username(update)

    # Already approved?
    cur.execute("SELECT 1 FROM approved_users WHERE chat_id = %s", (chat_id,))
    if cur.fetchone():
        return await update.message.reply_text("You are already approved.")

    # Already pending?
    cur.execute("SELECT 1 FROM pending_users WHERE chat_id = %s", (chat_id,))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO pending_users (chat_id, username)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (chat_id, username))

    await update.message.reply_text("Your registration request has been submitted.")

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"New registration:\nChat ID: {chat_id}\nUsername: @{username}"
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /approve <chat_id>")

    chat_id = int(context.args[0])

    cur.execute("SELECT * FROM pending_users WHERE chat_id = %s", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("User not found in pending list.")

    cur.execute("DELETE FROM pending_users WHERE chat_id = %s", (chat_id,))
    cur.execute("""
        INSERT INTO approved_users (chat_id, username)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (chat_id, user["username"]))

    await update.message.reply_text(f"Approved @{user['username']} ({chat_id}).")
    await context.bot.send_message(chat_id, "You have been approved for T‑School alerts!")

async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /deny <chat_id>")

    chat_id = int(context.args[0])

    cur.execute("DELETE FROM pending_users WHERE chat_id = %s RETURNING username", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("User not found in pending list.")

    await update.message.reply_text(f"Denied @{user['username']} ({chat_id}).")

async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    cur.execute("SELECT * FROM pending_users")
    pending = cur.fetchall()

    cur.execute("SELECT * FROM approved_users")
    approved = cur.fetchall()

    text = "<b>Pending users:</b>\n"
    if pending:
        for u in pending:
            text += f"- {u['chat_id']} (@{u['username']})\n"
    else:
        text += "– none –\n"

    text += "\n<b>Approved users:</b>\n"
    if approved:
        for u in approved:
            text += f"- {u['chat_id']} (@{u['username']})\n"
    else:
        text += "– none –"

    await update.message.reply_text(text, parse_mode="HTML")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /remove <chat_id>")

    chat_id = int(context.args[0])

    cur.execute("DELETE FROM approved_users WHERE chat_id = %s RETURNING username", (chat_id,))
    user = cur.fetchone()

    if not user:
        return await update.message.reply_text("User not found.")

    await update.message.reply_text(f"Removed @{user['username']} ({chat_id}).")
# -------------------------
# TICKER MANAGEMENT
# -------------------------

async def add_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /addticker <symbol>")

    symbol = context.args[0].upper()

    cur.execute("""
        INSERT INTO tickers (symbol)
        VALUES (%s)
        ON CONFLICT DO NOTHING
    """, (symbol,))

    await update.message.reply_text(f"Ticker {symbol} added.")


async def remove_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return await update.message.reply_text("You are not an admin.")

    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /removeticker <symbol>")

    symbol = context.args[0].upper()

    cur.execute("DELETE FROM tickers WHERE symbol = %s RETURNING symbol", (symbol,))
    deleted = cur.fetchone()

    if not deleted:
        return await update.message.reply_text("Ticker not found.")

    await update.message.reply_text(f"Ticker {symbol} removed.")


# -------------------------
# SUBSCRIPTIONS MENU
# -------------------------

async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Check approval
    if not is_approved(chat_id):
        if update.message:
            return await update.message.reply_text("You are not approved to use this bot.")
        else:
            return await update.callback_query.message.reply_text("You are not approved to use this bot.")

    # Fetch tickers
    cur.execute("SELECT symbol FROM tickers ORDER BY symbol ASC")
    all_tickers = [row["symbol"] for row in cur.fetchall()]

    # Fetch user subscriptions
    cur.execute("SELECT symbol FROM subscriptions WHERE chat_id = %s", (chat_id,))
    user_subs = {row["symbol"] for row in cur.fetchall()}

    # Build keyboard
    keyboard = []
    row = []

    for symbol in all_tickers:
        label = f"✅ {symbol}" if symbol in user_subs else f"❌ {symbol}"
        row.append(InlineKeyboardButton(label, callback_data=f"toggle:{symbol}"))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # --- Correct handling of message vs callback ---
    if update.message:
        # Called via /subscriptions
        await update.message.reply_text(
            "Select the tickers you want to receive alerts for:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Called via callback button
        await update.callback_query.message.edit_text(
            "Select the tickers you want to receive alerts for:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# -------------------------
# CALLBACK HANDLER
# -------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data

    if not data.startswith("toggle:"):
        return

    symbol = data.split(":", 1)[1]

    cur.execute("""
        SELECT 1 FROM subscriptions
        WHERE chat_id = %s AND symbol = %s
    """, (chat_id, symbol))
    exists = cur.fetchone()

    if exists:
        cur.execute("""
            DELETE FROM subscriptions
            WHERE chat_id = %s AND symbol = %s
        """, (chat_id, symbol))
    else:
        cur.execute("""
            INSERT INTO subscriptions (chat_id, symbol)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (chat_id, symbol))

    await subscriptions(update, context)
# -------------------------
# MAIN + WEBHOOK SERVER
# -------------------------

async def main():
    global telegram_app

    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # COMMAND HANDLERS
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("register", register))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("deny", deny))
    telegram_app.add_handler(CommandHandler("list", list_members))
    telegram_app.add_handler(CommandHandler("remove", remove))
    telegram_app.add_handler(CommandHandler("addticker", add_ticker))
    telegram_app.add_handler(CommandHandler("removeticker", remove_ticker))
    telegram_app.add_handler(CommandHandler("subscriptions", subscriptions))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))

    # AIOHTTP SERVER
    app = web.Application()
    app.router.add_post("/webhook", handle_tradingview)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)

    print(f"Server running on port {port}")
    await site.start()

    # START TELEGRAM BOT (zonder updater)
    await telegram_app.initialize()
    await telegram_app.start()

    # START DISPATCHER QUEUE WORKER
    telegram_app.create_task(telegram_app.process_update_queue())

    # Keep running forever
    await asyncio.Event().wait()



# -------------------------
# ENTRYPOINT
# -------------------------

if __name__ == "__main__":
    asyncio.run(main())
