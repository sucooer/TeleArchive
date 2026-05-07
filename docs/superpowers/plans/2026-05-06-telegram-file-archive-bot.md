# Telegram 文件转存 Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-owner Telegram Bot that automatically downloads forwarded files to the server filesystem, stores them in date-based directories, and appends JSONL index records with large-file-safe streaming downloads.

**Architecture:** The bot runs as one Python process using `python-telegram-bot` long polling. Message handlers validate the owner, extract a downloadable Telegram file, stream it to a `.part` file with `httpx`, then atomically rename it and append a JSONL audit record. Supporting modules isolate config loading, logging, storage naming, indexing, downloading, and Telegram handlers for testability.

**Tech Stack:** Python 3.11+, python-telegram-bot, httpx, python-dotenv, pytest

---

### Task 1: Scaffold project files and dependency manifest

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `README.md`
- Create: `bot/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write the failing scaffold test**

```python
# tests/test_scaffold.py
from pathlib import Path


def test_project_scaffold_files_exist():
    expected = [
        Path("requirements.txt"),
        Path(".env.example"),
        Path("README.md"),
        Path("bot/__init__.py"),
        Path("tests/__init__.py"),
    ]
    missing = [str(path) for path in expected if not path.exists()]
    assert missing == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffold.py -v`
Expected: FAIL with missing file assertions

- [ ] **Step 3: Write minimal scaffold files**

```text
# requirements.txt
python-telegram-bot==21.11.1
httpx==0.28.1
python-dotenv==1.0.1
pytest==8.3.5
```

```dotenv
# .env.example
BOT_TOKEN=123456:replace-me
OWNER_TELEGRAM_USER_ID=123456789
STORAGE_ROOT=./storage
INDEX_FILE=./data/index.jsonl
LOG_FILE=./logs/bot.log
HTTP_TIMEOUT=1800
CHUNK_SIZE=1048576
MAX_CONCURRENT_DOWNLOADS=1
```

```markdown
# README.md

Telegram file archive bot.
```

```python
# bot/__init__.py
"""Telegram file archive bot package."""
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scaffold.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example README.md bot/__init__.py tests/__init__.py tests/test_scaffold.py
git commit -m "chore: scaffold telegram archive bot project"
```

### Task 2: Add configuration loading and validation

**Files:**
- Create: `bot/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing config test**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from bot.config import Settings, load_settings


def test_load_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "42")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("INDEX_FILE", str(tmp_path / "data" / "index.jsonl"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("HTTP_TIMEOUT", "900")
    monkeypatch.setenv("CHUNK_SIZE", "4096")
    monkeypatch.setenv("MAX_CONCURRENT_DOWNLOADS", "1")

    settings = load_settings()

    assert settings == Settings(
        bot_token="token",
        owner_telegram_user_id=42,
        storage_root=tmp_path / "storage",
        index_file=tmp_path / "data" / "index.jsonl",
        log_file=tmp_path / "logs" / "bot.log",
        http_timeout=900.0,
        chunk_size=4096,
        max_concurrent_downloads=1,
    )


def test_load_settings_requires_bot_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "42")

    with pytest.raises(ValueError, match="BOT_TOKEN"):
        load_settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bot.config`

- [ ] **Step 3: Write minimal configuration module**

```python
# bot/config.py
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
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/config.py tests/test_config.py
git commit -m "feat: add environment configuration loader"
```

### Task 3: Add storage path planning and collision handling

**Files:**
- Create: `bot/storage.py`
- Create: `bot/types.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage test**

```python
# tests/test_storage.py
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.storage import build_storage_plan
from bot.types import ArchiveCandidate


def test_build_storage_plan_uses_date_directory(tmp_path):
    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name="report.pdf",
        file_size=12,
    )

    plan = build_storage_plan(
        storage_root=tmp_path,
        candidate=candidate,
        now=datetime(2026, 5, 6, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    assert plan.target_dir == tmp_path / "2026-05-06"
    assert plan.final_path == tmp_path / "2026-05-06" / "report.pdf"
    assert plan.part_path == tmp_path / "2026-05-06" / "report.pdf.part"


def test_build_storage_plan_generates_name_without_original_filename(tmp_path):
    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name=None,
        file_size=12,
    )

    plan = build_storage_plan(storage_root=tmp_path, candidate=candidate)

    assert plan.final_path.name == "file_unique-id"


def test_build_storage_plan_adds_suffix_when_name_exists(tmp_path):
    dated_dir = tmp_path / "2026-05-06"
    dated_dir.mkdir()
    (dated_dir / "report.pdf").write_bytes(b"old")

    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name="report.pdf",
        file_size=12,
    )

    plan = build_storage_plan(
        storage_root=tmp_path,
        candidate=candidate,
        now=datetime(2026, 5, 6, 10, 0),
    )

    assert plan.final_path.name.startswith("report__")
    assert plan.final_path.suffix == ".pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError` for storage modules

- [ ] **Step 3: Write minimal archive types and storage planning**

```python
# bot/types.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveCandidate:
    telegram_file_id: str
    telegram_file_unique_id: str
    original_file_name: str | None
    file_size: int | None


@dataclass(frozen=True)
class StoragePlan:
    target_dir: Path
    final_path: Path
    part_path: Path
```

```python
# bot/storage.py
from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from bot.types import ArchiveCandidate, StoragePlan


def build_storage_plan(
    storage_root: Path,
    candidate: ArchiveCandidate,
    now: datetime | None = None,
) -> StoragePlan:
    now = now or datetime.now()
    target_dir = storage_root / now.strftime("%Y-%m-%d")
    base_name = candidate.original_file_name or f"file_{candidate.telegram_file_unique_id}"

    final_path = target_dir / base_name
    if final_path.exists():
        suffix = "".join(final_path.suffixes)
        stem = final_path.name[: -len(suffix)] if suffix else final_path.name
        final_path = target_dir / f"{stem}__{secrets.token_hex(3)}{suffix}"

    return StoragePlan(
        target_dir=target_dir,
        final_path=final_path,
        part_path=target_dir / f"{final_path.name}.part",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/types.py bot/storage.py tests/test_storage.py
git commit -m "feat: add storage planning and collision handling"
```

### Task 4: Add JSONL indexing with parent directory creation

**Files:**
- Create: `bot/indexer.py`
- Create: `tests/test_indexer.py`

- [ ] **Step 1: Write the failing indexer test**

```python
# tests/test_indexer.py
import json

from bot.indexer import append_index_record


def test_append_index_record_creates_parent_directory_and_jsonl(tmp_path):
    index_file = tmp_path / "data" / "index.jsonl"
    record = {"saved_path": "storage/2026-05-06/report.pdf", "file_size": 123}

    append_index_record(index_file=index_file, record=record)

    lines = index_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_indexer.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bot.indexer`

- [ ] **Step 3: Write minimal JSONL indexer**

```python
# bot/indexer.py
from __future__ import annotations

import json
from pathlib import Path


def append_index_record(index_file: Path, record: dict) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with index_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_indexer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/indexer.py tests/test_indexer.py
git commit -m "feat: add jsonl archive indexing"
```

### Task 5: Add stream downloader with `.part` cleanup on failure

**Files:**
- Create: `bot/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing downloader test**

```python
# tests/test_downloader.py
from pathlib import Path

import pytest

from bot.downloader import stream_download_to_path


class FakeResponse:
    def __init__(self, chunks, raise_on_chunk=None):
        self._chunks = chunks
        self._raise_on_chunk = raise_on_chunk

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        for index, chunk in enumerate(self._chunks):
            if self._raise_on_chunk == index:
                raise RuntimeError("network broke")
            yield chunk


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    def __init__(self, response):
        self.response = response

    def stream(self, method, url):
        assert method == "GET"
        assert url == "https://example.test/file"
        return FakeStreamContext(self.response)


def test_stream_download_to_path_writes_chunks_and_renames(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"]))

    written = stream_download_to_path(
        client=client,
        url="https://example.test/file",
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
    )

    assert written == 6
    assert final_path.read_bytes() == b"abcdef"
    assert not part_path.exists()


def test_stream_download_to_path_removes_part_file_on_failure(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"], raise_on_chunk=1))

    with pytest.raises(RuntimeError, match="network broke"):
        stream_download_to_path(
            client=client,
            url="https://example.test/file",
            part_path=part_path,
            final_path=final_path,
            chunk_size=3,
        )

    assert not part_path.exists()
    assert not final_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_downloader.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bot.downloader`

- [ ] **Step 3: Write minimal streaming downloader**

```python
# bot/downloader.py
from __future__ import annotations

from pathlib import Path


def stream_download_to_path(
    client,
    url: str,
    part_path: Path,
    final_path: Path,
    chunk_size: int,
) -> int:
    bytes_written = 0
    part_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with part_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    handle.write(chunk)
                    bytes_written += len(chunk)
        part_path.replace(final_path)
        return bytes_written
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_downloader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/downloader.py tests/test_downloader.py
git commit -m "feat: add streaming file downloader"
```

### Task 6: Add logging setup

**Files:**
- Create: `bot/logging_setup.py`
- Create: `tests/test_logging_setup.py`

- [ ] **Step 1: Write the failing logging test**

```python
# tests/test_logging_setup.py
import logging

from bot.logging_setup import configure_logging


def test_configure_logging_creates_log_file_and_writes_message(tmp_path):
    log_file = tmp_path / "logs" / "bot.log"

    logger = configure_logging(log_file)
    logger.info("hello")

    contents = log_file.read_text(encoding="utf-8")
    assert "hello" in contents
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_setup.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bot.logging_setup`

- [ ] **Step 3: Write minimal logging configuration**

```python
# bot/logging_setup.py
from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("telegram_file_archive_bot")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_setup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/logging_setup.py tests/test_logging_setup.py
git commit -m "feat: add file logging setup"
```

### Task 7: Add Telegram file extraction helpers

**Files:**
- Create: `bot/handlers.py`
- Modify: `bot/types.py`
- Create: `tests/test_handlers_extract.py`

- [ ] **Step 1: Write the failing extraction test**

```python
# tests/test_handlers_extract.py
from types import SimpleNamespace

from bot.handlers import extract_archive_candidate


def test_extract_archive_candidate_from_document_message():
    message = SimpleNamespace(
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.pdf",
            file_size=12,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
    )

    candidate = extract_archive_candidate(message)

    assert candidate.telegram_file_id == "file-id"
    assert candidate.telegram_file_unique_id == "unique-id"
    assert candidate.original_file_name == "report.pdf"
    assert candidate.file_size == 12


def test_extract_archive_candidate_uses_largest_photo():
    message = SimpleNamespace(
        document=None,
        video=None,
        audio=None,
        voice=None,
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="small-u", file_size=10, width=10, height=10),
            SimpleNamespace(file_id="large", file_unique_id="large-u", file_size=100, width=100, height=100),
        ],
    )

    candidate = extract_archive_candidate(message)

    assert candidate.telegram_file_id == "large"
    assert candidate.original_file_name == "file_large-u"


def test_extract_archive_candidate_returns_none_for_non_file_message():
    message = SimpleNamespace(document=None, video=None, audio=None, voice=None, photo=None)

    assert extract_archive_candidate(message) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_extract.py -v`
Expected: FAIL with missing `extract_archive_candidate`

- [ ] **Step 3: Write minimal extraction helper**

```python
# bot/handlers.py
from __future__ import annotations

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers_extract.py
git commit -m "feat: add telegram file extraction helpers"
```

### Task 8: Add handler service flow for owner checks, save, and index

**Files:**
- Modify: `bot/handlers.py`
- Create: `tests/test_handlers_flow.py`

- [ ] **Step 1: Write the failing handler flow test**

```python
# tests/test_handlers_flow.py
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.config import Settings
from bot.handlers import ArchiveService
from bot.types import ArchiveCandidate


class StubDownloader:
    def __init__(self):
        self.calls = []

    def __call__(self, client, url, part_path, final_path, chunk_size):
        self.calls.append((url, part_path, final_path, chunk_size))
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"payload")
        return 7


class StubBotFile:
    file_path = "documents/report.pdf"


class StubBot:
    async def get_file(self, file_id):
        assert file_id == "file-id"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_flow.py -v`
Expected: FAIL with missing `ArchiveService`

- [ ] **Step 3: Write minimal archive service flow**

```python
# bot/handlers.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

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


class ArchiveService:
    def __init__(self, settings, downloader, logger, http_client):
        self.settings = settings
        self.downloader = downloader
        self.logger = logger
        self.http_client = http_client

    async def handle_message(self, message, bot) -> str:
        if message.from_user.id != self.settings.owner_telegram_user_id:
            return "无权使用此机器人"

        candidate = extract_archive_candidate(message)
        if candidate is None:
            return "请转发带文件的消息"

        telegram_file = await bot.get_file(candidate.telegram_file_id)
        download_url = f"https://api.telegram.org/file/bot{self.settings.bot_token}/{telegram_file.file_path}"
        storage_plan = build_storage_plan(self.settings.storage_root, candidate)
        bytes_written = self.downloader(
            client=self.http_client,
            url=download_url,
            part_path=storage_plan.part_path,
            final_path=storage_plan.final_path,
            chunk_size=self.settings.chunk_size,
        )

        record = {
            "downloaded_at": datetime.utcnow().isoformat(),
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
        return f"已保存: {storage_plan.final_path.name}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers_flow.py
git commit -m "feat: add archive service flow"
```

### Task 9: Add Telegram command and message entrypoints

**Files:**
- Modify: `bot/handlers.py`
- Create: `tests/test_handlers_entrypoints.py`

- [ ] **Step 1: Write the failing entrypoint test**

```python
# tests/test_handlers_entrypoints.py
from types import SimpleNamespace

import pytest

from bot.handlers import handle_start, handle_status, handle_archive_message


class DummyMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class DummyService:
    async def handle_message(self, message, bot):
        return "已保存: report.pdf"


@pytest.mark.asyncio
async def test_handle_start_replies_with_usage():
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(bot_data={"storage_root": "./storage"})

    await handle_start(update, context)

    assert "Telegram 文件转存" in message.replies[0]


@pytest.mark.asyncio
async def test_handle_status_replies_with_storage_root():
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(bot_data={"storage_root": "./storage", "today_count": 3})

    await handle_status(update, context)

    assert "./storage" in message.replies[0]
    assert "3" in message.replies[0]


@pytest.mark.asyncio
async def test_handle_archive_message_replies_with_service_result():
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(bot=object(), bot_data={"archive_service": DummyService()})

    await handle_archive_message(update, context)

    assert message.replies == ["已保存: report.pdf"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_entrypoints.py -v`
Expected: FAIL with missing handler entrypoints

- [ ] **Step 3: Write minimal entrypoint handlers**

```python
# bot/handlers.py
from __future__ import annotations

from datetime import datetime

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


class ArchiveService:
    def __init__(self, settings, downloader, logger, http_client):
        self.settings = settings
        self.downloader = downloader
        self.logger = logger
        self.http_client = http_client

    async def handle_message(self, message, bot) -> str:
        if message.from_user.id != self.settings.owner_telegram_user_id:
            return "无权使用此机器人"
        candidate = extract_archive_candidate(message)
        if candidate is None:
            return "请转发带文件的消息"

        telegram_file = await bot.get_file(candidate.telegram_file_id)
        download_url = f"https://api.telegram.org/file/bot{self.settings.bot_token}/{telegram_file.file_path}"
        storage_plan = build_storage_plan(self.settings.storage_root, candidate)
        bytes_written = self.downloader(
            client=self.http_client,
            url=download_url,
            part_path=storage_plan.part_path,
            final_path=storage_plan.final_path,
            chunk_size=self.settings.chunk_size,
        )
        record = {
            "downloaded_at": datetime.utcnow().isoformat(),
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
        return f"已保存: {storage_plan.final_path.name}"


async def handle_start(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    await update.message.reply_text(f"Telegram 文件转存 Bot\n存储目录: {storage_root}")


async def handle_status(update, context) -> None:
    storage_root = context.bot_data["storage_root"]
    today_count = context.bot_data["today_count"]
    await update.message.reply_text(f"运行正常\n存储目录: {storage_root}\n今日文件数: {today_count}")


async def handle_archive_message(update, context) -> None:
    service = context.bot_data["archive_service"]
    result = await service.handle_message(update.message, context.bot)
    await update.message.reply_text(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_entrypoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers_entrypoints.py
git commit -m "feat: add telegram command and message handlers"
```

### Task 10: Add application bootstrap and wiring

**Files:**
- Create: `bot/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write the failing app wiring test**

```python
# tests/test_app.py
from types import SimpleNamespace

from bot.app import build_runtime_objects
from bot.config import Settings


def test_build_runtime_objects_exposes_service_and_storage_root(tmp_path):
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

    runtime = build_runtime_objects(settings)

    assert "archive_service" in runtime
    assert runtime["storage_root"] == str(settings.storage_root)
    assert runtime["today_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError` for `bot.app`

- [ ] **Step 3: Write minimal bootstrap wiring**

```python
# bot/app.py
from __future__ import annotations

import httpx
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.config import load_settings
from bot.downloader import stream_download_to_path
from bot.handlers import ArchiveService, handle_archive_message, handle_start, handle_status
from bot.logging_setup import configure_logging


def build_runtime_objects(settings):
    logger = configure_logging(settings.log_file)
    http_client = httpx.Client(timeout=settings.http_timeout)
    archive_service = ArchiveService(
        settings=settings,
        downloader=stream_download_to_path,
        logger=logger,
        http_client=http_client,
    )
    return {
        "archive_service": archive_service,
        "storage_root": str(settings.storage_root),
        "today_count": 0,
    }


def build_application():
    settings = load_settings()
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data.update(build_runtime_objects(settings))
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(MessageHandler(filters.ALL, handle_archive_message))
    return application


def main():
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/app.py tests/test_app.py
git commit -m "feat: wire telegram bot application bootstrap"
```

### Task 11: Add status counting from JSONL and resilient archive error handling

**Files:**
- Modify: `bot/indexer.py`
- Modify: `bot/handlers.py`
- Modify: `bot/app.py`
- Create: `tests/test_status_and_errors.py`

- [ ] **Step 1: Write the failing status/error tests**

```python
# tests/test_status_and_errors.py
import json
from datetime import date
from types import SimpleNamespace

import pytest

from bot.config import Settings
from bot.handlers import ArchiveService
from bot.indexer import count_records_for_day


def test_count_records_for_day_reads_matching_dates(tmp_path):
    index_file = tmp_path / "data" / "index.jsonl"
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        "\n".join(
            [
                json.dumps({"downloaded_at": "2026-05-06T10:00:00"}),
                json.dumps({"downloaded_at": "2026-05-06T11:00:00"}),
                json.dumps({"downloaded_at": "2026-05-07T09:00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert count_records_for_day(index_file, date(2026, 5, 6)) == 2


class ExplodingDownloader:
    def __call__(self, client, url, part_path, final_path, chunk_size):
        raise RuntimeError("download failed")


class StubBotFile:
    file_path = "documents/report.pdf"


class StubBot:
    async def get_file(self, file_id):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_status_and_errors.py -v`
Expected: FAIL with missing `count_records_for_day` and unhandled exception behavior

- [ ] **Step 3: Extend indexer, service error handling, and status initialization**

```python
# bot/indexer.py
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def append_index_record(index_file: Path, record: dict) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with index_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def count_records_for_day(index_file: Path, target_day: date) -> int:
    if not index_file.exists():
        return 0

    count = 0
    with index_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            downloaded_at = str(record.get("downloaded_at", ""))
            if downloaded_at.startswith(target_day.isoformat()):
                count += 1
    return count
```

```python
# bot/handlers.py
from __future__ import annotations

from datetime import datetime

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


class ArchiveService:
    def __init__(self, settings, downloader, logger, http_client):
        self.settings = settings
        self.downloader = downloader
        self.logger = logger
        self.http_client = http_client

    async def handle_message(self, message, bot) -> str:
        if message.from_user.id != self.settings.owner_telegram_user_id:
            return "无权使用此机器人"
        candidate = extract_archive_candidate(message)
        if candidate is None:
            return "请转发带文件的消息"

        try:
            telegram_file = await bot.get_file(candidate.telegram_file_id)
            download_url = f"https://api.telegram.org/file/bot{self.settings.bot_token}/{telegram_file.file_path}"
            storage_plan = build_storage_plan(self.settings.storage_root, candidate)
            bytes_written = self.downloader(
                client=self.http_client,
                url=download_url,
                part_path=storage_plan.part_path,
                final_path=storage_plan.final_path,
                chunk_size=self.settings.chunk_size,
            )
            record = {
                "downloaded_at": datetime.utcnow().isoformat(),
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
            return f"已保存: {storage_plan.final_path.name}"
        except Exception as exc:
            return f"下载失败: {exc}"
```

```python
# bot/app.py
from __future__ import annotations

from datetime import date

import httpx
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.config import load_settings
from bot.downloader import stream_download_to_path
from bot.handlers import ArchiveService, handle_archive_message, handle_start, handle_status
from bot.indexer import count_records_for_day
from bot.logging_setup import configure_logging


def build_runtime_objects(settings):
    logger = configure_logging(settings.log_file)
    http_client = httpx.Client(timeout=settings.http_timeout)
    archive_service = ArchiveService(
        settings=settings,
        downloader=stream_download_to_path,
        logger=logger,
        http_client=http_client,
    )
    return {
        "archive_service": archive_service,
        "storage_root": str(settings.storage_root),
        "today_count": count_records_for_day(settings.index_file, date.today()),
    }


def build_application():
    settings = load_settings()
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data.update(build_runtime_objects(settings))
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(MessageHandler(filters.ALL, handle_archive_message))
    return application


def main():
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_status_and_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/indexer.py bot/handlers.py bot/app.py tests/test_status_and_errors.py
git commit -m "feat: add status counting and download error replies"
```

### Task 12: Add deployment assets and end-to-end documentation

**Files:**
- Create: `systemd/telegram-file-archive-bot.service`
- Modify: `README.md`
- Create: `tests/test_deployment_assets.py`

- [ ] **Step 1: Write the failing deployment asset test**

```python
# tests/test_deployment_assets.py
from pathlib import Path


def test_deployment_assets_exist_and_reference_python_module():
    service_file = Path("systemd/telegram-file-archive-bot.service")
    readme = Path("README.md")

    assert service_file.exists()
    assert "python -m bot.app" in service_file.read_text(encoding="utf-8")
    assert "BOT_TOKEN" in readme.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py -v`
Expected: FAIL with missing service file or README content

- [ ] **Step 3: Write deployment files and usage docs**

```ini
# systemd/telegram-file-archive-bot.service
[Unit]
Description=Telegram File Archive Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/telegram-file-archive-bot
EnvironmentFile=/opt/telegram-file-archive-bot/.env
ExecStart=/usr/bin/python3 -m bot.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```markdown
# README.md

## Telegram 文件转存 Bot

### 环境变量

- `BOT_TOKEN`
- `OWNER_TELEGRAM_USER_ID`
- `STORAGE_ROOT`
- `INDEX_FILE`
- `LOG_FILE`
- `HTTP_TIMEOUT`
- `CHUNK_SIZE`
- `MAX_CONCURRENT_DOWNLOADS`

### 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m bot.app
```

### systemd

复制 `systemd/telegram-file-archive-bot.service` 到 `/etc/systemd/system/` 后启用服务。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_deployment_assets.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS for all tests

- [ ] **Step 6: Commit**

```bash
git add systemd/telegram-file-archive-bot.service README.md tests/test_deployment_assets.py
git commit -m "docs: add deployment assets and usage guide"
```
