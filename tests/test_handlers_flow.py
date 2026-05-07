import json
from types import SimpleNamespace

import pytest

from bot.config import Settings
from bot.handlers import ArchiveService, resolve_download_url


class StubDownloader:
    def __init__(self):
        self.calls = []

    async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None):
        self.calls.append((url, part_path, final_path, chunk_size))
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"payload")
        return 7


class StubBotFile:
    file_path = "documents/report.pdf"


class StubBot:
    async def get_file(self, file_id, **kwargs):
        _ = kwargs
        assert file_id == "file-id"
        return StubBotFile()


class StubAbsoluteUrlBotFile:
    file_path = "https://api.telegram.org/file/bottoken/photos/file_10480.jpg"


class StubAbsoluteUrlBot:
    async def get_file(self, file_id, **kwargs):
        _ = kwargs
        assert file_id == "file-id"
        return StubAbsoluteUrlBotFile()


class StubPhotoBotFile:
    file_path = "https://api.telegram.org/file/bottoken/photos/file_10480.jpg"


class StubPhotoBot:
    async def get_file(self, file_id, **kwargs):
        _ = kwargs
        assert file_id == "large"
        return StubPhotoBotFile()


class RecordingTimeoutBot:
    def __init__(self):
        self.kwargs = None

    async def get_file(self, file_id, **kwargs):
        self.kwargs = kwargs
        return StubBotFile()


@pytest.mark.asyncio
async def test_archive_service_rejects_non_owner(tmp_path):
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
    service = ArchiveService(settings=settings, downloader=StubDownloader(), logger=None, http_client=None)
    message = SimpleNamespace(from_user=SimpleNamespace(id=7))

    reply = await service.handle_message(message=message, bot=StubBot())

    assert reply == "无权使用此机器人"


@pytest.mark.asyncio
async def test_archive_service_replies_for_non_file_message(tmp_path):
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
    service = ArchiveService(settings=settings, downloader=StubDownloader(), logger=None, http_client=None)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=None,
        video=None,
        audio=None,
        voice=None,
        photo=None,
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=1, title="chat", type="private"),
    )

    reply = await service.handle_message(message=message, bot=StubBot())

    assert reply == "请转发带文件的消息"


@pytest.mark.asyncio
async def test_archive_service_downloads_and_indexes_file(tmp_path):
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
    downloader = StubDownloader()
    service = ArchiveService(settings=settings, downloader=downloader, logger=None, http_client=None)
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
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    reply = await service.handle_message(message=message, bot=StubBot())

    assert reply.startswith("已保存:")
    lines = settings.index_file.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    assert record["telegram_file_id"] == "file-id"
    assert record["source_chat_id"] == 99
    assert "report.pdf" in record["saved_file_name"]




@pytest.mark.asyncio
async def test_archive_service_uses_absolute_file_url_without_prefixing(tmp_path):
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
    downloader = StubDownloader()
    service = ArchiveService(settings=settings, downloader=downloader, logger=None, http_client=None)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.jpg",
            file_size=7,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    await service.handle_message(message=message, bot=StubAbsoluteUrlBot())

    assert downloader.calls[0][0] == "https://api.telegram.org/file/bottoken/photos/file_10480.jpg"


@pytest.mark.asyncio
async def test_archive_service_adds_extension_for_photo_without_filename(tmp_path):
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
    downloader = StubDownloader()
    service = ArchiveService(settings=settings, downloader=downloader, logger=None, http_client=None)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=None,
        video=None,
        audio=None,
        voice=None,
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="small-u", file_size=10, width=10, height=10),
            SimpleNamespace(file_id="large", file_unique_id="AQAD-hBrG3JImVd-", file_size=100, width=100, height=100),
        ],
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    reply = await service.handle_message(message=message, bot=StubPhotoBot())

    assert "file_AQAD-hBrG3JImVd-.jpg" in reply
    lines = settings.index_file.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    assert record["saved_file_name"].endswith(".jpg")


def test_resolve_download_url_keeps_local_file_path(tmp_path):
    local_file = tmp_path / "telegram-file.bin"
    local_file.write_bytes(b"abc")

    assert resolve_download_url("token", str(local_file)) == str(local_file)


@pytest.mark.asyncio
async def test_archive_service_passes_extended_timeouts_to_get_file(tmp_path):
    settings = Settings(
        bot_token="token",
        owner_telegram_user_id=42,
        storage_root=tmp_path / "storage",
        index_file=tmp_path / "data" / "index.jsonl",
        log_file=tmp_path / "logs" / "bot.log",
        http_timeout=900.0,
        chunk_size=4096,
        max_concurrent_downloads=1,
        bot_api_base_url="https://api.telegram.org/bot",
        bot_api_base_file_url="https://api.telegram.org/file/bot",
    )
    bot = RecordingTimeoutBot()
    service = ArchiveService(settings=settings, downloader=StubDownloader(), logger=None, http_client=None)
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
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    await service.handle_message(message=message, bot=bot)

    assert bot.kwargs["read_timeout"] == 900.0
    assert bot.kwargs["write_timeout"] == 900.0
    assert bot.kwargs["pool_timeout"] == 900.0

