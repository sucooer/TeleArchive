import json
from types import SimpleNamespace

import pytest

from bot.config import Settings
from bot.handlers import ArchiveService
from bot.indexer import count_records_for_day


class ExplodingDownloader:
    async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None, is_cancelled=None):
        _ = progress_callback
        _ = is_cancelled
        raise RuntimeError("download failed")


class StubBotFile:
    file_path = "documents/report.pdf"


class StubBot:
    async def get_file(self, file_id, **kwargs):
        _ = kwargs
        return StubBotFile()


@pytest.mark.asyncio
async def test_archive_service_returns_error_message_on_download_failure(tmp_path):
    settings = Settings(
        bot_token="token",
        owner_telegram_user_id=42,
        storage_root=tmp_path / "storage",
        index_file=tmp_path / "data" / "index.jsonl",
        log_file=tmp_path / "logs" / "bot.log",
        http_timeout=900.0,
        chunk_size=4096,
        max_concurrent_downloads=1,
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.pdf",
            file_size=7,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
        date=None,
    )
    service = ArchiveService(settings=settings, downloader=ExplodingDownloader(), logger=None, http_client=None)

    reply = await service.handle_message(message=message, bot=StubBot())

    assert reply == "下载失败: download failed"
    assert not settings.index_file.exists()


def test_count_records_for_day_missing_file_returns_zero(tmp_path):
    assert count_records_for_day(tmp_path / "missing.jsonl", __import__("datetime").date(2026, 5, 6)) == 0
