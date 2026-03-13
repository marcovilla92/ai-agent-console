"""Bot configuration."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    bot_token: str = ""


def get_settings() -> Settings:
    return Settings(
        bot_token=os.environ.get("BOT_TOKEN", ""),
    )
