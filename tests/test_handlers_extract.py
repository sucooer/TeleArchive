from types import SimpleNamespace

from bot.handlers import extract_archive_candidate


def test_extract_archive_candidate_from_document_message():
    message = SimpleNamespace(
        document=SimpleNamespace(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="report.pdf",
            file_size=12,
        ),
        video=None,
        audio=None,
        voice=None,
        photo=None,
    )

    candidate = extract_archive_candidate(message)

    assert candidate.telegram_file_id == "file-id"
    assert candidate.telegram_file_unique_id == "unique-id"
    assert candidate.original_file_name == "report.pdf"
    assert candidate.file_size == 12


def test_extract_archive_candidate_uses_largest_photo():
    message = SimpleNamespace(
        document=None,
        video=None,
        audio=None,
        voice=None,
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="small-u", file_size=10, width=10, height=10),
            SimpleNamespace(file_id="large", file_unique_id="large-u", file_size=100, width=100, height=100),
        ],
    )

    candidate = extract_archive_candidate(message)

    assert candidate.telegram_file_id == "large"
    assert candidate.original_file_name == "file_large-u"


def test_extract_archive_candidate_returns_none_for_non_file_message():
    message = SimpleNamespace(document=None, video=None, audio=None, voice=None, photo=None)

    assert extract_archive_candidate(message) is None
