from types import SimpleNamespace

import pytest

from bot.handlers import handle_archive_message, handle_cancel_download, handle_start, handle_status


class DummyMessage:
    def __init__(self):
        self.replies = []
        self.status_messages = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        status_message = DummyStatusMessage(text, kwargs.get("reply_markup"))
        self.status_messages.append(status_message)
        return status_message


class DummyStatusMessage:
    def __init__(self, text, reply_markup=None):
        self.text = text
        self.edits = []
        self.reply_markup = reply_markup

    async def edit_text(self, text, **kwargs):
        self.text = text
        self.edits.append(text)
        self.reply_markup = kwargs.get("reply_markup")


class DummyService:
    def __init__(self):
        self.calls = []
        self.task_id_factory = lambda: "task-1"

    async def handle_message(self, message, bot, status_message_factory=None, task_id=None):
        self.calls.append((message, bot, status_message_factory, task_id))
        return "已保存: report.pdf"


class DummyApplication:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro):
        class DummyTask:
            def __init__(self, coro):
                self.coro = coro
                self.cancelled = False

            def cancel(self):
                self.cancelled = True

            def __await__(self):
                return self.coro.__await__()

        task = DummyTask(coro)
        self.tasks.append(task)
        return task


class DummyCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.message = DummyStatusMessage("下载中")

    async def answer(self, text):
        self.answers.append(text)


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
    application = DummyApplication()
    context = SimpleNamespace(bot=object(), bot_data={"archive_service": service}, application=application)

    await handle_archive_message(update, context)

    assert len(application.tasks) == 1
    await application.tasks[0]
    assert message.replies == ["已保存: report.pdf"]
    assert service.calls == [(message, context.bot, message.reply_text, "task-1")]


@pytest.mark.asyncio
async def test_handle_cancel_download_marks_task_cancelled():
    callback_query = DummyCallbackQuery("cancel_download:task-1")
    update = SimpleNamespace(callback_query=callback_query)

    class CancellableTask:
        def __init__(self):
            self.cancel_called = False

        def cancel(self):
            self.cancel_called = True

    task = CancellableTask()
    context = SimpleNamespace(
        bot_data={"active_downloads": {"task-1": {"cancelled": False, "status_message": callback_query.message, "task": task}}}
    )

    await handle_cancel_download(update, context)

    assert context.bot_data["active_downloads"]["task-1"]["cancelled"] is True
    assert task.cancel_called is True
    assert callback_query.answers == ["正在取消下载…"]
    assert callback_query.message.edits[-1] == "已取消"
