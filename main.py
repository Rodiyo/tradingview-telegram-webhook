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
