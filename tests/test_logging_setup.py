from bot.logging_setup import configure_logging


def test_configure_logging_creates_log_file_and_writes_message(tmp_path):
    log_file = tmp_path / "logs" / "bot.log"

    logger = configure_logging(log_file)
    logger.info("hello")

    contents = log_file.read_text(encoding="utf-8")
    assert "hello" in contents
