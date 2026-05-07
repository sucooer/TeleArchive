# Telegram 文件转存 Bot

把你转发给机器人的 Telegram 文件自动下载到服务器本地磁盘。

## 环境变量

- `BOT_TOKEN`
- `OWNER_TELEGRAM_USER_ID`
- `STORAGE_ROOT`
- `INDEX_FILE`
- `LOG_FILE`
- `HTTP_TIMEOUT`
- `CHUNK_SIZE`
- `MAX_CONCURRENT_DOWNLOADS`
- `BOT_API_BASE_URL`
- `BOT_API_BASE_FILE_URL`

## 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m bot.app
```

## systemd

复制 `systemd/telegram-file-archive-bot.service` 到 `/etc/systemd/system/` 后启用服务。

## 大文件下载

默认接入 `https://api.telegram.org` 时，Telegram Bot API 对 `getFile` 下载大小有限制。要支持大文件，需要把 Bot 切到你自己部署的 Local Bot API Server，并启用 `--local`。

切换后把 `.env` 改成类似：

```dotenv
BOT_API_BASE_URL=http://127.0.0.1:8081/bot
BOT_API_BASE_FILE_URL=http://127.0.0.1:8081/file/bot
```

当前代码已经同时支持：

- 远程 Bot API 返回的 HTTP 文件地址
- Local Bot API `--local` 返回的绝对本地文件路径
