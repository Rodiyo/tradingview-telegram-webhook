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

    # Start TradingView webhook server in aparte thread
    threading.Thread(target=start_webhook_server, daemon=True).start()

    # Start Telegram polling
    telegram_app.run_polling()
