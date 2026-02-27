import threading

def main():
    global telegram_app
    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ... al je handlers ...

    # Start webhook server in aparte thread
    threading.Thread(target=start_webhook_server, daemon=True).start()

    # Start Telegram polling
    telegram_app.run_polling()
