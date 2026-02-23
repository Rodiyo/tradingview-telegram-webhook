# TradingView → Telegram Webhook Bot (Python FastAPI)

## Environment variables
- TELEGRAM_TOKEN
- CHAT_ID

## Run locally
uvicorn main:app --reload

## Deploy on Railway
1. Create new project → Empty Service
2. Connect Repo
3. Add environment variables:
   - TELEGRAM_TOKEN = jouw bot token
   - CHAT_ID = 1604766930
4. Deploy
5. Generate Domain
6. Use: https://<jouw-domain>.railway.app/webhook in TradingView
