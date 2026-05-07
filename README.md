# TeleArchive

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Telegram-Bot%20API-blue?style=flat-square&logo=telegram" alt="Telegram Bot API">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License MIT">
</p>

<p align="center">
  A lightweight Telegram bot that automatically downloads and archives files to your local server.
</p>

---

## ✨ Features

- 📥 **Automatic File Archival** — Forward any file to the bot and it's saved instantly
- 📊 **Smart Progress Display** — Real-time download progress with speed and percentage
- 🗂️ **Date-Based Organization** — Files sorted into `YYYY-MM-DD` directories
- 📦 **Large File Support** — Streaming downloads for files of any size
- 🎛️ **Cancel Anytime** — Cancel ongoing downloads with a single tap
- 📝 **Audit Trail** — JSONL index for all archived files
- 🔒 **Single-User Mode** — Only the owner can use the bot

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather))

### Installation

```bash
# Clone the repository
git clone https://github.com/sucooer/TeleArchive.git
cd TeleArchive

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```dotenv
BOT_TOKEN=your_bot_token_here
OWNER_TELEGRAM_USER_ID=your_telegram_user_id
STORAGE_ROOT=./storage
INDEX_FILE=./data/index.jsonl
LOG_FILE=./logs/bot.log
HTTP_TIMEOUT=900.0
CHUNK_SIZE=8192
MAX_CONCURRENT_DOWNLOADS=1
```

> **Tip:** Use `cp .env.example .env` and edit the values.

### Run

```bash
python -m bot.app
```

## 🐳 Docker Deployment

### Deployment Modes

This project supports three practical deployment shapes:

1. Start only `telearchive` and use Telegram official Bot API.
2. Start only `telearchive` and connect it to an existing `telegram-bot-api` service.
3. Start `telearchive` and `telegram-bot-api` together with `docker compose`.

The main difference is whether file downloads go through the official Bot API or a local Bot API server. Large file support requires a local Bot API server and `BOT_API_LOCAL_MODE=1`.

### Mode 1: Start Only TeleArchive

Use this when you only need the archive bot and are fine with the official Bot API limits.

1. Prepare configuration:

```bash
cp .env.example .env
```

2. Edit `.env` and keep the default Bot API settings:

```dotenv
BOT_TOKEN=your_bot_token_here
OWNER_TELEGRAM_USER_ID=your_telegram_user_id
STORAGE_ROOT=/media/tg
INDEX_FILE=./data/index.jsonl
LOG_FILE=./logs/bot.log
BOT_API_BASE_URL=https://api.telegram.org/bot
BOT_API_BASE_FILE_URL=https://api.telegram.org/file/bot
BOT_API_LOCAL_MODE=0
```

3. Build and run only the bot container:

```bash
docker build -t telearchive .

docker run -d \
  --name telearchive \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v /media/tg:/media/tg \
  telearchive
```

4. Check logs:

```bash
docker logs -f telearchive
```

This mode is simple, but Telegram official Bot API may reject large files with `File is too big`.

### Mode 2: Start Only TeleArchive and Connect to an Existing Bot API Server

Use this when you already run `telegram-bot-api` somewhere else and want this project to start only the archive bot.

If the existing Bot API server is reachable over HTTP, configure `.env` like this:

```dotenv
BOT_TOKEN=your_bot_token_here
OWNER_TELEGRAM_USER_ID=your_telegram_user_id
STORAGE_ROOT=/media/tg
INDEX_FILE=./data/index.jsonl
LOG_FILE=./logs/bot.log
BOT_API_BASE_URL=http://host.docker.internal:8081/bot
BOT_API_BASE_FILE_URL=http://host.docker.internal:8081/file/bot
BOT_API_LOCAL_MODE=1
```

On Linux, add host mapping when starting the container:

```bash
docker run -d \
  --name telearchive \
  --restart unless-stopped \
  --env-file .env \
  --add-host=host.docker.internal:host-gateway \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v /media/tg:/media/tg \
  telearchive
```

If the existing Bot API server runs with `--local`, `getFile` can return local filesystem paths. In that case, TeleArchive must see the same Bot API data directory at the same path:

```bash
EXTERNAL_BOT_API_DATA=/var/lib/telegram-bot-api

docker run -d \
  --name telearchive \
  --restart unless-stopped \
  --env-file .env \
  --add-host=host.docker.internal:host-gateway \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v /media/tg:/media/tg \
  -v ${EXTERNAL_BOT_API_DATA}:/var/lib/telegram-bot-api:ro \
  telearchive
```

If the existing Bot API server is on another Docker network, attach the TeleArchive container to that network and set:

```dotenv
BOT_API_BASE_URL=http://telegram-bot-api:8081/bot
BOT_API_BASE_FILE_URL=http://telegram-bot-api:8081/file/bot
BOT_API_LOCAL_MODE=1
```

### Mode 3: Start TeleArchive and Bot API Together

Use this when you want a self-contained deployment with large file support managed by this repository.

1. Prepare configuration:

```bash
cp .env.example .env
```

2. Edit `.env`:

```dotenv
BOT_TOKEN=your_bot_token_here
OWNER_TELEGRAM_USER_ID=your_telegram_user_id
STORAGE_ROOT=/media/tg
INDEX_FILE=./data/index.jsonl
LOG_FILE=./logs/bot.log
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

3. Start both services:

```bash
docker compose up -d --build
```

4. Check status:

```bash
docker compose ps
docker compose logs -f telearchive
docker compose logs -f telegram-bot-api
```

In this mode, `docker-compose.yml` intentionally overrides these values for `telearchive`:

```dotenv
BOT_API_BASE_URL=http://telegram-bot-api:8081/bot
BOT_API_BASE_FILE_URL=http://telegram-bot-api:8081/file/bot
BOT_API_LOCAL_MODE=1
```

It also mounts the Bot API cache volume into the TeleArchive container as read-only, and mounts host `/media/tg` into container `/media/tg` so `STORAGE_ROOT=/media/tg` writes directly to the host.

### Start Only telegram-bot-api

Use this when you want to provide a local Bot API service for another app or for Mode 2 above.

```bash
docker run -d \
  --name telegram-bot-api \
  --restart unless-stopped \
  -p 8081:8081 \
  -v telegram-bot-api-data:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=your_api_id \
  -e TELEGRAM_API_HASH=your_api_hash \
  -e TELEGRAM_LOCAL=1 \
  -e TELEGRAM_HTTP_PORT=8081 \
  aiogram/telegram-bot-api:latest
```

If you later want TeleArchive to use this instance, point `BOT_API_BASE_URL` and `BOT_API_BASE_FILE_URL` to it and set `BOT_API_LOCAL_MODE=1`.

## 📦 Large File Support

Telegram official Bot API (`https://api.telegram.org`) has file download limits. To handle large files reliably, use a local Bot API server and enable local mode in TeleArchive:

```dotenv
BOT_API_BASE_URL=http://127.0.0.1:8081/bot
BOT_API_BASE_FILE_URL=http://127.0.0.1:8081/file/bot
BOT_API_LOCAL_MODE=1
```

For the bundled Compose deployment, the equivalent values are injected automatically with service hostname `telegram-bot-api`.

## ⚙️ Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot token from [@BotFather](https://t.me/BotFather) | *Required* |
| `OWNER_TELEGRAM_USER_ID` | Your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot)) | *Required* |
| `STORAGE_ROOT` | Root directory for file storage | `./storage` |
| `INDEX_FILE` | Path to the JSONL index file | `./data/index.jsonl` |
| `LOG_FILE` | Path to the log file | `./logs/bot.log` |
| `HTTP_TIMEOUT` | HTTP timeout in seconds for downloads | `900.0` |
| `CHUNK_SIZE` | Chunk size in bytes for streaming downloads | `8192` |
| `MAX_CONCURRENT_DOWNLOADS` | Max concurrent downloads (v1 uses serial) | `1` |
| `TELEGRAM_API_ID` | Telegram app API ID for the Local Bot API server | Required for Compose large file mode |
| `TELEGRAM_API_HASH` | Telegram app API hash for the Local Bot API server | Required for Compose large file mode |
| `BOT_API_BASE_URL` | Bot API method endpoint prefix | `https://api.telegram.org/bot` |
| `BOT_API_BASE_FILE_URL` | Bot API file download endpoint prefix | `https://api.telegram.org/file/bot` |
| `BOT_API_LOCAL_MODE` | Enable python-telegram-bot local Bot API mode for local servers | `0` |

## 🔧 Running as a Service (Linux)

This repository no longer ships a fixed `systemd` unit file. Create one yourself so paths, user, Python environment, and storage directory match your machine.

Example unit:

```ini
[Unit]
Description=TeleArchive Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/your-user/TeleArchive
EnvironmentFile=/home/your-user/TeleArchive/.env
ExecStart=/home/your-user/TeleArchive/.venv/bin/python -m bot.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save it as `/etc/systemd/system/telearchive.service`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telearchive
sudo systemctl start telearchive
sudo systemctl status telearchive
```

## 📖 How It Works

```
┌─────────────────┐     Forward      ┌──────────────────┐
│  Telegram Chat  │ ───────────────► │  TeleArchive Bot │
└─────────────────┘                  └──────────────────┘
        │                                      │
        │                                      ▼
        │                              ┌──────────────────┐
        │                              │  Extract File    │
        │                              │  & Check Owner   │
        │                              └──────────────────┘
        │                                      │
        │                                      ▼
        │                              ┌──────────────────┐
        │                              │  Stream Download │
        │                              │  to Local Disk   │
        │                              └──────────────────┘
        │                                      │
        │                                      ▼
        │                              ┌──────────────────┐
        │                              │  Save & Index    │
        │                              │  storage/YYYY-MM-DD/ │
        └─────────────────────────────► │  Reply Success  │
                                       └──────────────────┘
```

## 📝 Index Format

Each archived file creates a JSONL record:

```json
{
  "downloaded_at": "2026-05-07T12:00:00+00:00",
  "saved_path": "storage/2026-05-07/document.pdf",
  "original_file_name": "document.pdf",
  "saved_file_name": "document.pdf",
  "file_size": 1048576,
  "telegram_file_id": "AgACAgIx...",
  "telegram_file_unique_id": "AQAD...",
  "source_chat_id": -1001234567890,
  "source_chat_title": "My Channel",
  "source_chat_type": "channel",
  "forward_date": "2026-05-07T10:00:00",
  "sender_user_id": 123456789
}
```

## 🛠️ Tech Stack

- **Python 3.11+** — Core language
- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)** — Telegram Bot API framework
- **httpx** — Async HTTP client for streaming downloads
- **python-dotenv** — Environment configuration

## 📜 License

This project is licensed under the MIT License — see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

---

<p align="center">
  Made with ❤️ for Telegram power users
</p>
