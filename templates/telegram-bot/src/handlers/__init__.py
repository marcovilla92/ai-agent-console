"""Handler registration."""
from telegram.ext import Application, CommandHandler


async def start(update, context):
    await update.message.reply_text("Hello! Bot is running.")


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
