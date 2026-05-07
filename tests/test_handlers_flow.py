import json
from itertools import count
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup

from bot.config import Settings
from bot.handlers import ArchiveService, build_prepare_text, resolve_download_url


class StubDownloader:
    def __init__(self):
        self.calls = []

    async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None, is_cancelled=None, prepare_callback=None, expected_size=None):
        self.calls.append((url, part_path, final_path, chunk_size))
        _ = progress_callback
        _ = is_cancelled
        _ = prepare_callback
        _ = expected_size
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


class RecordingStatusMessage:
    def __init__(self, text):
        self.text = text
        self.edits = []
        self.reply_markup = None

    async def edit_text(self, text, **kwargs):
        self.text = text
        self.edits.append(text)
        self.reply_markup = kwargs.get("reply_markup")


class RecordingStatusFactory:
    def __init__(self):
        self.calls = []
        self.status_message = None

    async def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        self.status_message = RecordingStatusMessage(text)
        self.status_message.reply_markup = kwargs.get("reply_markup")
        return self.status_message


class ProgressDownloader:
    def __init__(self, points):
        self.points = points

    async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None, is_cancelled=None, prepare_callback=None, expected_size=None):
        _ = client
        _ = url
        _ = chunk_size
        _ = prepare_callback
        _ = expected_size
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"payload")
        for point in self.points:
            if is_cancelled and is_cancelled():
                from bot.downloader import DownloadCancelled

                raise DownloadCancelled(point)
            if progress_callback is not None:
                await progress_callback(point)
        return self.points[-1] if self.points else 0


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

    assert reply.startswith("✅ 已保存:")
    lines = settings.index_file.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    assert record["telegram_file_id"] == "file-id"
    assert record["source_chat_id"] == 99
    assert "report.pdf" in record["saved_file_name"]


@pytest.mark.asyncio
async def test_archive_service_status_message_contains_cancel_button(tmp_path):
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
    status_factory = RecordingStatusFactory()
    active_downloads = {}
    service = ArchiveService(
        settings=settings,
        downloader=StubDownloader(),
        logger=None,
        http_client=None,
        active_downloads=active_downloads,
        task_id_factory=lambda: "task-1",
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
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    await service.handle_message(message=message, bot=StubBot(), status_message_factory=status_factory)

    reply_markup = status_factory.calls[0][1]["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    assert reply_markup.inline_keyboard[0][0].text == "取消下载"
    assert status_factory.calls[0][0].startswith("📥 分片下载中 ")
    assert "🧩 正在等待 Telegram 返回可读分片…" in status_factory.calls[0][0]


@pytest.mark.asyncio
async def test_archive_service_cancellation_edits_message_and_clears_task(tmp_path):
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

    class CancellingDownloader:
        async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None, is_cancelled=None, prepare_callback=None, expected_size=None):
            part_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.write_bytes(b"partial")
            active_downloads["task-1"]["cancelled"] = True
            _ = progress_callback
            _ = prepare_callback
            _ = expected_size
            if is_cancelled and is_cancelled():
                from bot.downloader import DownloadCancelled

                raise DownloadCancelled()
            return 3

    status_factory = RecordingStatusFactory()
    active_downloads = {}
    service = ArchiveService(
        settings=settings,
        downloader=CancellingDownloader(),
        logger=None,
        http_client=None,
        active_downloads=active_downloads,
        task_id_factory=lambda: "task-1",
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
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    result = await service.handle_message(message=message, bot=StubBot(), status_message_factory=status_factory)

    assert result is None
    assert status_factory.status_message.edits[-1] == "已取消"
    assert status_factory.status_message.reply_markup is None
    assert active_downloads == {}


@pytest.mark.asyncio
async def test_archive_service_updates_progress_with_10_cell_bar(tmp_path):
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
    status_factory = RecordingStatusFactory()
    clock = iter([100.0, 100.0, 100.0, 102.1, 102.1, 104.2])
    service = ArchiveService(
        settings=settings,
        downloader=ProgressDownloader([30, 100]),
        logger=None,
        http_client=None,
        active_downloads={},
        task_id_factory=lambda: "task-1",
        time_source=lambda: next(clock),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.pdf",
            file_size=100,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    result = await service.handle_message(message=message, bot=StubBot(), status_message_factory=status_factory)

    assert result is None
    assert any("合并中 report.pdf" in text for text in status_factory.status_message.edits)
    assert any("███░░░░░░░ 30%" in text for text in status_factory.status_message.edits)
    assert status_factory.status_message.edits[-1].startswith("✅ 已保存:")


def test_build_progress_text_uses_reasonable_speed_from_recent_window():
    from bot.handlers import build_progress_text

    text = build_progress_text(
        "合并中",
        file_name="report.bin",
        downloaded_bytes=2 * 1024 * 1024 * 1024,
        total_bytes=3 * 1024 * 1024 * 1024,
        started_at=100.0,
        now=101.0,
        recent_bytes=16 * 1024 * 1024,
        recent_elapsed=2.0,
    )

    assert "合并中 report.bin" in text
    assert "⚡ 8.0 MB/s" in text
    assert "67%" in text


def test_build_prepare_text_without_waiting_seconds():
    text = build_prepare_text("report.bin", started_at=100.0, now=112.4)

    assert text == "📥 分片下载中 report.bin\n🧩 正在等待 Telegram 返回可读分片…"


@pytest.mark.asyncio
async def test_archive_service_updates_progress_before_large_jump_to_70_percent(tmp_path):
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
    status_factory = RecordingStatusFactory()
    clock = iter([100.0, 100.0, 100.0, 100.3, 100.6, 100.9, 101.2, 101.5])
    service = ArchiveService(
        settings=settings,
        downloader=ProgressDownloader([40, 400 * 1024 * 1024, 2 * 1024 * 1024 * 1024]),
        logger=None,
        http_client=None,
        active_downloads={},
        task_id_factory=lambda: "task-1",
        time_source=lambda: next(clock),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="ABFC.mp4",
            file_size=3 * 1024 * 1024 * 1024,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    result = await service.handle_message(message=message, bot=StubBot(), status_message_factory=status_factory)

    assert result is None
    assert any("13%" in text for text in status_factory.status_message.edits)


@pytest.mark.asyncio
async def test_archive_service_cancelled_state_blocks_later_progress_updates(tmp_path):
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

    class CancelThenProgressDownloader:
        async def __call__(self, client, url, part_path, final_path, chunk_size, progress_callback=None, is_cancelled=None, prepare_callback=None, expected_size=None):
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(b"payload")
            _ = prepare_callback
            _ = expected_size
            if progress_callback is not None:
                await progress_callback(30)
            active_downloads["task-1"]["cancelled"] = True
            if is_cancelled and is_cancelled():
                from bot.downloader import DownloadCancelled

                raise DownloadCancelled(30)
            return 30

    status_factory = RecordingStatusFactory()
    active_downloads = {}
    service = ArchiveService(
        settings=settings,
        downloader=CancelThenProgressDownloader(),
        logger=None,
        http_client=None,
        active_downloads=active_downloads,
        task_id_factory=lambda: "task-1",
        time_source=lambda: 100.0,
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.pdf",
            file_size=100,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
        forward_origin=None,
        date=None,
        chat=SimpleNamespace(id=99, title="archive", type="private"),
    )

    await service.handle_message(message=message, bot=StubBot(), status_message_factory=status_factory)

    assert status_factory.status_message.edits[-1] == "已取消"




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
