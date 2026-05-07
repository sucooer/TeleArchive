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
    monkeypatch.setenv("BOT_API_BASE_URL", "https://api.telegram.org/bot")
    monkeypatch.setenv("BOT_API_BASE_FILE_URL", "https://api.telegram.org/file/bot")

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
        bot_api_base_url="https://api.telegram.org/bot",
        bot_api_base_file_url="https://api.telegram.org/file/bot",
    )


def test_load_settings_requires_bot_token(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "42")

    with pytest.raises(ValueError, match="BOT_TOKEN"):
        load_settings()
