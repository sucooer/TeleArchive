from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bot.indexer import append_index_record
from bot.storage import build_storage_plan
from bot.types import ArchiveCandidate


def extract_archive_candidate(message) -> ArchiveCandidate | None:
    media = message.document or message.video or message.audio or message.voice
    if media is not None:
        return ArchiveCandidate(
            telegram_file_id=media.file_id,
            telegram_file_unique_id=media.file_unique_id,
            original_file_name=getattr(media, "file_name", None),
            file_size=getattr(media, "file_size", None),
        )

    if message.photo:
        largest = max(message.photo, key=lambda item: (item.width * item.height, item.file_size or 0))
        return ArchiveCandidate(
            telegram_file_id=largest.file_id,
            telegram_file_unique_id=largest.file_unique_id,
            original_file_name=f"file_{largest.file_unique_id}",
            file_size=getattr(largest, "file_size", None),
        )

    return None


def resolve_download_url(bot_token: str, file_path: str) -> str:
    if Path(file_path).is_file():
        return file_path
    parsed = urlparse(file_path)
    if parsed.scheme and parsed.netloc:
        return file_path
    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"


def apply_file_path_name_hint(candidate: ArchiveCandidate, file_path: str) -> ArchiveCandidate:
    current_name = candidate.original_file_name
    parsed = urlparse(file_path)
    hinted_suffix = Path(parsed.path).suffix
    if not hinted_suffix:
        return candidate

    if not current_name:
        return replace(candidate, original_file_name=f"file_{candidate.telegram_file_unique_id}{hinted_suffix}")

    current_suffix = Path(current_name).suffix
    if current_suffix:
        return candidate

    return replace(candidate, original_file_name=f"{current_name}{hinted_suffix}")


def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"

    value = float(num_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def build_progress_text(
    file_name: str,
    downloaded_bytes: int,
    total_bytes: int | None,
    started_at: float,
    now: float,
) -> str:
    elapsed = max(now - started_at, 0.001)
    speed = downloaded_bytes / elapsed
    downloaded_text = format_size(downloaded_bytes)
    speed_text = f"{format_size(int(speed))}/s"

    if total_bytes:
        percent = min(downloaded_bytes / total_bytes * 100, 100.0)
        filled_cells = min(int(percent / 100 * 20), 20)
        progress_bar = f"{'█' * filled_cells}{'░' * (20 - filled_cells)}"
        total_text = format_size(total_bytes)
        return (
            f"下载中: {file_name}\n"
            f"{progress_bar} {percent:.0f}%\n"
            f"{speed_text} | {downloaded_text} / {total_text}"
        )

    return f"下载中: {file_name}\n{downloaded_text} | {speed_text}"


def is_temporary_file_unavailable_error(exc: Exception) -> bool:
    message = str(exc)
    return "Wrong file_id or the file is temporarily unavailable" in message


class ArchiveService:
    def __init__(self, settings, downloader, logger, http_client, time_source=None):
        self.settings = settings
        self.downloader = downloader
        self.logger = logger
        self.http_client = http_client
        self.time_source = time_source

    async def handle_message(self, message, bot, progress_message_factory=None, task_id=None) -> str | None:
        if message.from_user.id != self.settings.owner_telegram_user_id:
            if self.logger:
                self.logger.info("Rejected user %s", message.from_user.id)
            return "无权使用此机器人"

        candidate = extract_archive_candidate(message)
        if candidate is None:
            return "请转发带文件的消息"

        try:
            last_get_file_error = None
            telegram_file = None
            for attempt in range(3):
                try:
                    telegram_file = await bot.get_file(
                        candidate.telegram_file_id,
                        read_timeout=self.settings.http_timeout,
                        write_timeout=self.settings.http_timeout,
                        pool_timeout=self.settings.http_timeout,
                    )
                    break
                except Exception as exc:
                    last_get_file_error = exc
                    if not is_temporary_file_unavailable_error(exc) or attempt == 2:
                        raise
                    if self.logger:
                        self.logger.warning("Temporary get_file failure, retry %s: %s", attempt + 1, exc)
                    await asyncio.sleep(1)

            if telegram_file is None and last_get_file_error is not None:
                raise last_get_file_error
            candidate = apply_file_path_name_hint(candidate, telegram_file.file_path)
            download_url = resolve_download_url(self.settings.bot_token, telegram_file.file_path)
            storage_plan = build_storage_plan(self.settings.storage_root, candidate)

            bytes_written = await self.downloader(
                client=self.http_client,
                url=download_url,
                part_path=storage_plan.part_path,
                final_path=storage_plan.final_path,
                chunk_size=self.settings.chunk_size,
            )
            record = {
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "saved_path": str(storage_plan.final_path),
                "original_file_name": candidate.original_file_name,
                "saved_file_name": storage_plan.final_path.name,
                "file_size": candidate.file_size if candidate.file_size is not None else bytes_written,
                "telegram_file_id": candidate.telegram_file_id,
                "telegram_file_unique_id": candidate.telegram_file_unique_id,
                "source_chat_id": getattr(message.chat, "id", None),
                "source_chat_title": getattr(message.chat, "title", None),
                "source_chat_type": getattr(message.chat, "type", None),
                "forward_date": message.date.isoformat() if getattr(message, "date", None) else None,
                "sender_user_id": message.from_user.id,
            }
            append_index_record(self.settings.index_file, record)
            if self.logger:
                self.logger.info("Saved file to %s", storage_plan.final_path)

            return f"已保存: {storage_plan.final_path.name}\n大小: {format_size(record['file_size'])}\n目录: {storage_plan.final_path.parent.name}"
        except Exception as exc:
            if self.logger:
                self.logger.exception("Download failed")
            return f"下载失败: {exc}"


async def handle_start(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    await update.message.reply_text(f"Telegram 文件转存 Bot\n存储目录: {storage_root}")


async def handle_status(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    today_count = context.bot_data["today_count"]
    await update.message.reply_text(f"运行正常\n存储目录: {storage_root}\n今日文件数: {today_count}")


async def handle_archive_message(update, context) -> None:
    service = context.bot_data["archive_service"]
    result = await service.handle_message(
        update.message,
        context.bot,
        progress_message_factory=update.message.reply_text,
    )
    if result is not None:
        await update.message.reply_text(result)
