from types import SimpleNamespace

import pytest

from bot.handlers import handle_archive_message, handle_start, handle_status


class DummyMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        _ = kwargs
        self.replies.append(text)


class DummyService:
    def __init__(self):
        self.calls = []

    async def handle_message(self, message, bot, progress_message_factory=None):
        self.calls.append((message, bot, progress_message_factory))
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
    service = DummyService()
    context = SimpleNamespace(bot=object(), bot_data={"archive_service": service})

    await handle_archive_message(update, context)

    assert message.replies == ["已保存: report.pdf"]
    assert service.calls == [(message, context.bot, message.reply_text)]
