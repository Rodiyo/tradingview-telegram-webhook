import os
import json
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))

APPROVED_FILE = "approved.json"
SUBSCRIPTIONS_FILE = "subscriptions.json"


def load_json(filename, default):
    if not os.path.exists(filename):
        return default
    with open(filename, "r") as f:
        return json.load(f)


@app.get("/")
def home():
    return {"status": "running"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # Expecting something like:
    # { "ticker": "NQ1", "message": "Some signal" }
    ticker = data.get("ticker")
    message = data.get("message", str(data))

    # Always send to admin (full payload context)
    admin_text = message if not ticker else f"[{ticker}] {message}"
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": ADMIN_CHAT_ID, "text": admin_text},
    )

    # Load approved users (list of dicts: {chat_id, username})
    approved = load_json(APPROVED_FILE, [])
    # Load subscriptions: { "chat_id": ["NQ1", "ES1", ...] }
    subscriptions = load_json(SUBSCRIPTIONS_FILE, {})

    # If no ticker is provided, fallback to old behavior: send to all approved
    if not ticker:
        for user in approved:
            chat_id = user["chat_id"]
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": message},
                )
            except:
                pass
        return {"status": "sent_broadcast_no_ticker"}

    # If ticker is provided: send only to users subscribed to that ticker
    for user in approved:
        chat_id = user["chat_id"]
        user_subs = subscriptions.get(str(chat_id), [])

        if ticker in user_subs:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": f"[{ticker}] {message}"},
                )
            except:
                pass

    return {"status": "sent_filtered", "ticker": ticker}
