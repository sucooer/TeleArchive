from pathlib import Path


def test_deployment_assets_exist_and_reference_python_module():
    readme = Path("README.md")

    assert "BOT_TOKEN" in readme.read_text(encoding="utf-8")
    assert "python -m bot.app" in readme.read_text(encoding="utf-8")
    assert "systemd" in readme.read_text(encoding="utf-8")


def test_docker_compose_shares_local_bot_api_data_with_telearchive():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "TELEGRAM_LOCAL: \"1\"" in compose
    assert "TELEGRAM_HTTP_PORT: \"8081\"" in compose
    assert "/media/tg:/media/tg" in compose
    assert "source: telegram-bot-api-data" in compose
    assert "target: /var/lib/telegram-bot-api" in compose
    assert "read_only: true" in compose
    assert "BOT_API_BASE_FILE_URL: http://telegram-bot-api:8081/file/bot" in compose


def test_readme_documents_connecting_to_existing_bot_api_server():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Connect to an Existing Bot API Server" in readme
    assert "EXTERNAL_BOT_API_DATA" in readme
    assert "BOT_API_BASE_URL=http://host.docker.internal:8081/bot" in readme
