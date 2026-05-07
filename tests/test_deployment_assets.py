from pathlib import Path


def test_deployment_assets_exist_and_reference_python_module():
    service_file = Path("systemd/telearchive.service")
    readme = Path("README.md")

    assert service_file.exists()
    assert "bot.app" in service_file.read_text(encoding="utf-8")
    assert "TeleArchive" in service_file.read_text(encoding="utf-8")
    assert "BOT_TOKEN" in readme.read_text(encoding="utf-8")
