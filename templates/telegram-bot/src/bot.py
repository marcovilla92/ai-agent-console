"""Telegram bot entry point."""
import logging

from telegram.ext import ApplicationBuilder

from src.config import get_settings
from src.handlers import register_handlers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main():
    settings = get_settings()
    app = ApplicationBuilder().token(settings.bot_token).build()
    register_handlers(app)
    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
