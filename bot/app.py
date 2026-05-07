from __future__ import annotations

from datetime import date

import httpx
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.config import load_settings
from bot.downloader import stream_download_to_path
from bot.handlers import ArchiveService, handle_archive_message, handle_cancel_download, handle_start, handle_status
from bot.indexer import count_records_for_day
from bot.logging_setup import configure_logging


def build_runtime_objects(settings):
    logger = configure_logging(settings.log_file)
    http_client = httpx.AsyncClient(timeout=settings.http_timeout)
    active_downloads = {}
    archive_service = ArchiveService(
        settings=settings,
        downloader=stream_download_to_path,
        logger=logger,
        http_client=http_client,
        active_downloads=active_downloads,
    )
    return {
        "archive_service": archive_service,
        "active_downloads": active_downloads,
        "storage_root": str(settings.storage_root),
        "today_count": count_records_for_day(settings.index_file, date.today()),
    }


def build_application():
    settings = load_settings()
    application = (
        Application.builder()
        .token(settings.bot_token)
        .base_url(settings.bot_api_base_url)
        .base_file_url(settings.bot_api_base_file_url)
        .local_mode(settings.bot_api_local_mode)
        .build()
    )
    application.bot_data.update(build_runtime_objects(settings))
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CallbackQueryHandler(handle_cancel_download, pattern=r"^cancel_download:"))
    application.add_handler(MessageHandler(filters.ALL, handle_archive_message))
    return application


def main():
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
