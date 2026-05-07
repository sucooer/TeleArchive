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

### Quick Start with Docker Compose

1. Clone and configure:
   ```bash
   git clone https://github.com/sucooer/TeleArchive.git
   cd TeleArchive
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```dotenv
   BOT_TOKEN=your_bot_token_here
   OWNER_TELEGRAM_USER_ID=your_telegram_user_id
   TELEGRAM_API_ID=your_api_id        # Get from https://my.telegram.org/apps
   TELEGRAM_API_HASH=your_api_hash    # Get from https://my.telegram.org/apps
   ```

3. Start the services:
   ```bash
   docker-compose up -d
   ```

4. View logs:
   ```bash
   docker-compose logs -f telearchive
   ```

### Services Included

| Service | Description |
|---------|-------------|
| `telearchive` | The Telegram file archive bot |
| `telegram-bot-api` | Local Bot API Server for large file support |

### Manual Docker Build

```bash
# Build the image
docker build -t telearchive .

# Run with environment file
docker run -d \
  --name telearchive \
  --env-file .env \
  -v $(pwd)/storage:/app/storage \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  telearchive
```

> **Note:** The `telegram-bot-api` service requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [my.telegram.org/apps](https://my.telegram.org/apps).

## 📦 Large File Support

By default, Telegram's official Bot API (`https://api.telegram.org`) limits file downloads. For large files, deploy your own **Local Bot API Server**:

### Using Docker (Recommended)

```bash
docker run -d \
  --name telegram-bot-api \
  -p 8081:8081 \
  -v telegram-bot-api-data:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=your_api_id \
  -e TELEGRAM_API_HASH=your_api_hash \
  aiogram/telegram-bot-api:latest \
  --local
```

> 📦 **Docker Image:** [aiogram/telegram-bot-api](https://hub.docker.com/r/aiogram/telegram-bot-api/tags)
>
> 📖 **Official Docs:** [Telegram Bot API - Running Locally](https://core.telegram.org/bots/api#running-a-local-server)

### Update `.env` for Local API

```dotenv
BOT_API_BASE_URL=http://127.0.0.1:8081/bot
BOT_API_BASE_FILE_URL=http://127.0.0.1:8081/file/bot
```

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

## 🔧 Running as a Service (Linux)

1. Copy the systemd service file:
   ```bash
   sudo cp systemd/telearchive.service /etc/systemd/system/
   ```

2. Reload systemd and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable telearchive
   sudo systemctl start telearchive
   ```

3. Check status:
   ```bash
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
