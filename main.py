from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# Vul deze in via Railway → Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") 
CHAT_ID = os.getenv("CHAT_ID")

@app.get("/")
def home():
    return {"status": "running"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # TradingView stuurt meestal JSON, dus we pakken de message of de hele payload
    message = data.get("message", str(data))

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(telegram_url, json=payload)

    return {"status": "sent"}
