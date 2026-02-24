import os
import json
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID"))

APPROVED_FILE = "approved.json"


def load_list(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r") as f:
        return json.load(f)


@app.get("/")
def home():
    return {"status": "running"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", str(data))

    # Stuur altijd naar jou (admin)
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": ADMIN_CHAT_ID, "text": message},
    )

    # Broadcast naar alle approved members
    approved = load_list(APPROVED_FILE)
    for user_id in approved:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": user_id, "text": message},
            )
        except:
            pass

    return {"status": "sent"}
