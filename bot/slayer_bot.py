        import os
        import logging
        import threading
        import time
        from telegram import Bot
        from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
        from telegram.error import TelegramError, NetworkError
        import asyncio

        # Import your other modules to avoid circular references
        import bot.command_handler as command_handler
        from bot.music_player import setup_music_handlers
        from bot.ai_conversation import setup_ai_handlers
        from bot.auto_responses import setup_auto_responses
        from bot.sudo_auth import setup_sudo_handlers
        from bot.ban import setup_ban_handlers
        from bot.gban import setup_gban_handlers

        # Configure logging
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        logger = logging.getLogger(__name__)

        # Global variables to store bot instances
        application = None
        bot = None
        bot_thread = None
        bot_status = {
            "running": False,
            "start_time": None,
            "error": None,
            "commands_processed": 0,
            "messages_processed": 0,
            "songs_played": 0,
            "ai_conversations": 0
        }

        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Log errors caused by updates."""
            logger.error(f"Update {update} caused error {context.error}")
            bot_status["error"] = str(context.error)

        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Send a welcome message when the command /start is issued."""
            user = update.effective_user
            await update.message.reply_text(
                f"Hello {user.first_name}! 🤖 I'm Slayer, an AI-powered music bot."
            )
            bot_status["commands_processed"] += 1

        # Other command functions...

        def setup_basic_handlers(application):
            """Set up basic command handlers."""
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("ping", ping_command))
            application.add_handler(CommandHandler("about", about_command))
            application.add_error_handler(error_handler)

        def initialize_bot(restart=False, production_mode=False):
            """Initialize or restart the Telegram bot."""
            global application, bot, bot_thread, bot_status

            logger.info(f"{'Restarting' if restart else 'Initializing'} the Telegram bot...")

            try:
                # Load the STRING_SESSION from the environment variable
                string_session = os.getenv('STRING_SESSION')

                if not string_session:
                    error_msg = "STRING_SESSION environment variable not set!"
                    logger.error(error_msg)
                    bot_status["error"] = error_msg
                    bot_status["running"] = False
                    return False

                logger.info(f"Found STRING_SESSION: {'Yes' if string_session else 'No'}")

                if production_mode:
                    logger.info("Starting bot in PRODUCTION mode (connecting to Telegram API)")

                    # Initialize the bot with the StringSession
                    application = Application.builder().bot(Bot(token=None, session=string_session)).build()

                    # Setup handlers
                    setup_basic_handlers(application)
                    setup_music_handlers(application)
                    setup_ai_handlers(application)
                    setup_ban_handlers(application)
                    setup_gban_handlers(application)
                    setup_auto_responses(application)
                    setup_sudo_handlers(application)

                    # Start the bot in a separate thread
                    bot_thread = threading.Thread(target=run_bot, args=(application,))
                    bot_thread.daemon = True
                    bot_thread.start()
                else:
                    logger.info("Starting bot in demo mode for web deployment")

                bot_status["running"] = True
                bot_status["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                bot_status["error"] = None
                logger.info("Bot initialized successfully!")
                return True

            except Exception as e:
                error_msg = f"Failed to {'restart' if restart else 'initialize'} bot: {str(e)}"
                logger.error(error_msg)
                bot_status["error"] = error_msg
                bot_status["running"] = False
                return False

        def run_bot(application):
            """Run the bot in the specified application."""
            try:
                asyncio.run(application.updater.start_polling())
                logger.info("Bot polling started successfully")
            except Exception as e:
                logger.error(f"Error in bot polling loop: {e}")
                bot_status["error"] = str(e)
                bot_status["running"] = False

        # Entry point of the bot when the script is executed
        if __name__ == "__main__":
            initialize_bot(production_mode=True)  # Set this to False for demo mode
