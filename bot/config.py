from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_telegram_user_id: int
    storage_root: Path
    index_file: Path
    log_file: Path
    http_timeout: float
    chunk_size: int
    max_concurrent_downloads: int
    bot_api_base_url: str = "https://api.telegram.org/bot"
    bot_api_base_file_url: str = "https://api.telegram.org/file/bot"
    bot_api_local_mode: bool = False


def parse_bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")
    owner = os.getenv("OWNER_TELEGRAM_USER_ID")
    if not bot_token:
        raise ValueError("BOT_TOKEN is required")
    if not owner:
        raise ValueError("OWNER_TELEGRAM_USER_ID is required")

    return Settings(
        bot_token=bot_token,
        owner_telegram_user_id=int(owner),
        storage_root=Path(os.getenv("STORAGE_ROOT", "./storage")),
        index_file=Path(os.getenv("INDEX_FILE", "./data/index.jsonl")),
        log_file=Path(os.getenv("LOG_FILE", "./logs/bot.log")),
        http_timeout=float(os.getenv("HTTP_TIMEOUT", "1800")),
        chunk_size=int(os.getenv("CHUNK_SIZE", str(1024 * 1024))),
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1")),
        bot_api_base_url=os.getenv("BOT_API_BASE_URL", "https://api.telegram.org/bot"),
        bot_api_base_file_url=os.getenv("BOT_API_BASE_FILE_URL", "https://api.telegram.org/file/bot"),
        bot_api_local_mode=parse_bool_env(os.getenv("BOT_API_LOCAL_MODE")),
    )
