from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.downloader import DownloadCancelled
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
    phase_label: str,
    file_name: str,
    downloaded_bytes: int,
    total_bytes: int | None,
    started_at: float,
    now: float,
    recent_bytes: int | None = None,
    recent_elapsed: float | None = None,
) -> str:
    if recent_bytes is not None and recent_elapsed is not None:
        speed = recent_bytes / max(recent_elapsed, 0.001)
    else:
        elapsed = max(now - started_at, 0.001)
        speed = downloaded_bytes / elapsed
    downloaded_text = format_size(downloaded_bytes)
    speed_text = f"{format_size(int(speed))}/s"

    if total_bytes:
        percent = min(downloaded_bytes / total_bytes * 100, 100.0)
        filled_cells = min(int(percent / 100 * 10), 10)
        progress_bar = f"{'█' * filled_cells}{'░' * (10 - filled_cells)}"
        total_text = format_size(total_bytes)
        return (
            f"{phase_label} {file_name}\n"
            f"{progress_bar} {percent:.0f}%\n"
            f"⚡ {speed_text} | 📦 {downloaded_text} / {total_text}"
        )

    return f"{phase_label} {file_name}\n⚡ {speed_text} | 📦 {downloaded_text}"


def build_prepare_text(file_name: str, started_at: float, now: float) -> str:
    return f"📥 分片下载中 {file_name}\n🧩 正在等待 Telegram 返回可读分片…"


def is_temporary_file_unavailable_error(exc: Exception) -> bool:
    message = str(exc)
    return "Wrong file_id or the file is temporarily unavailable" in message


class ArchiveService:
    def __init__(
        self,
        settings,
        downloader,
        logger,
        http_client,
        time_source=None,
        active_downloads=None,
        task_id_factory=None,
    ):
        self.settings = settings
        self.downloader = downloader
        self.logger = logger
        self.http_client = http_client
        self.time_source = time_source or monotonic
        self.active_downloads = active_downloads if active_downloads is not None else {}
        self.task_id_factory = task_id_factory or (lambda: uuid4().hex)

    async def _safe_edit_text(self, status_message, text: str, reply_markup=None) -> None:
        try:
            await status_message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            if self.logger:
                self.logger.warning("Status message update failed", exc_info=True)

    async def handle_message(self, message, bot, status_message_factory=None, task_id=None) -> str | None:
        if message.from_user.id != self.settings.owner_telegram_user_id:
            if self.logger:
                self.logger.info("Rejected user %s", message.from_user.id)
            return "无权使用此机器人"

        candidate = extract_archive_candidate(message)
        if candidate is None:
            return "请转发带文件的消息"

        try:
            task_id = task_id or self.task_id_factory()
            status_message = None
            started_at = self.time_source() if self.time_source else 0.0
            last_progress_update_at = started_at
            last_prepare_update_at = started_at
            last_progress_percent = 0.0
            if status_message_factory is not None:
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("取消下载", callback_data=f"cancel_download:{task_id}")]]
                )
                initial_text = build_prepare_text(
                    candidate.original_file_name or "file",
                    started_at,
                    started_at,
                )
                status_message = await status_message_factory(initial_text, reply_markup=reply_markup)
                self.active_downloads[task_id] = {
                    "cancelled": False,
                    "status_message": status_message,
                    "task": None,
                }

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
                    if self.active_downloads.get(task_id, {}).get("cancelled", False):
                        raise DownloadCancelled()
                    if not is_temporary_file_unavailable_error(exc) or attempt == 2:
                        raise
                    if self.logger:
                        self.logger.warning("Temporary get_file failure for task %s, retry %s: %s", task_id, attempt + 1, exc)
                    await asyncio.sleep(1)

            if telegram_file is None and last_get_file_error is not None:
                raise last_get_file_error
            if self.active_downloads.get(task_id, {}).get("cancelled", False):
                raise DownloadCancelled()
            candidate = apply_file_path_name_hint(candidate, telegram_file.file_path)
            download_url = resolve_download_url(self.settings.bot_token, telegram_file.file_path)
            storage_plan = build_storage_plan(self.settings.storage_root, candidate)

            recent_bytes_start = 0
            recent_time_start = started_at

            async def _update_status(phase_label: str, downloaded_bytes: int, current_time: float) -> None:
                nonlocal last_progress_update_at, last_progress_percent, recent_bytes_start, recent_time_start
                if status_message is None:
                    return
                if self.active_downloads.get(task_id, {}).get("cancelled", False):
                    return
                current_percent = 0.0
                if candidate.file_size:
                    current_percent = min(downloaded_bytes / candidate.file_size * 100, 100.0)

                should_update_by_time = current_time - last_progress_update_at >= 0.5
                should_update_by_percent = candidate.file_size is not None and current_percent - last_progress_percent >= 1.0
                should_update_by_bytes = downloaded_bytes - recent_bytes_start >= 8 * 1024 * 1024
                if not should_update_by_time and not should_update_by_percent and not should_update_by_bytes:
                    return

                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("取消下载", callback_data=f"cancel_download:{task_id}")]]
                )
                progress_text = build_progress_text(
                    phase_label,
                    candidate.original_file_name or "file",
                    downloaded_bytes,
                    candidate.file_size,
                    started_at,
                    current_time,
                    recent_bytes=downloaded_bytes - recent_bytes_start,
                    recent_elapsed=current_time - recent_time_start,
                )
                await self._safe_edit_text(status_message, progress_text, reply_markup=reply_markup)
                last_progress_update_at = current_time
                last_progress_percent = current_percent
                recent_bytes_start = downloaded_bytes
                recent_time_start = current_time

            async def prepare_callback(downloaded_bytes: int) -> None:
                pass

            async def progress_callback(downloaded_bytes: int) -> None:
                current_time = self.time_source() if self.time_source else started_at
                await _update_status("合并中", downloaded_bytes, current_time)

            bytes_written = await self.downloader(
                client=self.http_client,
                url=download_url,
                part_path=storage_plan.part_path,
                final_path=storage_plan.final_path,
                chunk_size=self.settings.chunk_size,
                progress_callback=progress_callback,
                is_cancelled=lambda: self.active_downloads.get(task_id, {}).get("cancelled", False),
                prepare_callback=prepare_callback,
                expected_size=candidate.file_size,
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

            result_text = f"✅ 已保存: {storage_plan.final_path.name}\n📦 大小: {format_size(record['file_size'])}\n📁 目录: {storage_plan.final_path.parent.name}"
            self.active_downloads.pop(task_id, None)
            if status_message is not None:
                await self._safe_edit_text(status_message, result_text, reply_markup=None)
                return None
            return result_text
        except DownloadCancelled as exc:
            if self.logger:
                self.logger.info("Download cancelled for task %s after %s bytes", task_id, exc.bytes_written)
            self.active_downloads.pop(task_id, None)
            if 'status_message' in locals() and status_message is not None:
                await self._safe_edit_text(status_message, "已取消", reply_markup=None)
                if self.logger:
                    self.logger.info("Cancel message set to cancelled for task %s", task_id)
                return None
            return "已取消"
        except asyncio.CancelledError:
            if self.logger:
                self.logger.info("Download task cancelled for task %s", task_id)
            self.active_downloads.pop(task_id, None)
            if 'status_message' in locals() and status_message is not None:
                await self._safe_edit_text(status_message, "已取消", reply_markup=None)
                if self.logger:
                    self.logger.info("Cancel message set to cancelled for task %s", task_id)
                return None
            return "已取消"
        except Exception as exc:
            if self.active_downloads.get(task_id, {}).get("cancelled", False):
                self.active_downloads.pop(task_id, None)
                if 'status_message' in locals() and status_message is not None:
                    await self._safe_edit_text(status_message, "已取消", reply_markup=None)
                    if self.logger:
                        self.logger.info("Cancel message set to cancelled for task %s", task_id)
                    return None
                return "已取消"
            if self.logger:
                self.logger.exception("Download failed")
            self.active_downloads.pop(task_id, None)
            error_text = f"下载失败: {exc}"
            if 'status_message' in locals() and status_message is not None:
                await self._safe_edit_text(status_message, error_text, reply_markup=None)
                return None
            return error_text


async def handle_start(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    await update.message.reply_text(f"Telegram 文件转存 Bot\n存储目录: {storage_root}")


async def handle_status(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    today_count = context.bot_data["today_count"]
    await update.message.reply_text(f"运行正常\n存储目录: {storage_root}\n今日文件数: {today_count}")


async def handle_archive_message(update, context) -> None:
    service = context.bot_data["archive_service"]
    task_id = service.task_id_factory()
    active_downloads = context.bot_data.setdefault("active_downloads", {})

    async def run_download():
        result = await service.handle_message(
            update.message,
            context.bot,
            status_message_factory=update.message.reply_text,
            task_id=task_id,
        )
        if result is not None:
            await update.message.reply_text(result)

    task = context.application.create_task(run_download())
    if task_id in active_downloads:
        active_downloads[task_id]["task"] = task
    else:
        active_downloads[task_id] = {"cancelled": False, "task": task}


async def handle_cancel_download(update, context) -> None:
    callback_query = update.callback_query
    task_id = callback_query.data.split(":", 1)[1]
    task = context.bot_data["active_downloads"].get(task_id)
    if task is None:
        await callback_query.answer("任务已结束")
        return

    if task.get("cancelled"):
        await callback_query.answer("正在取消下载…")
        return

    task["cancelled"] = True
    status_message = task.get("status_message")
    if status_message is not None:
        await status_message.edit_text("已取消", reply_markup=None)
        archive_service = context.bot_data.get("archive_service")
        if archive_service and archive_service.logger:
            archive_service.logger.info("Cancel message set to cancelled immediately for task %s", task_id)
    running_task = task.get("task")
    if running_task is not None:
        running_task.cancel()
    await callback_query.answer("正在取消下载…")
