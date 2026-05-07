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
        bot_api_base_url="https://api.telegram.org/bot",
        bot_api_base_file_url="https://api.telegram.org/file/bot",
    )

    runtime = build_runtime_objects(settings)

    assert "archive_service" in runtime
    assert runtime["storage_root"] == str(settings.storage_root)
    assert runtime["today_count"] == 0
