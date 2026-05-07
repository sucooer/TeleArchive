from datetime import datetime
from zoneinfo import ZoneInfo

from bot.storage import build_storage_plan
from bot.types import ArchiveCandidate


def test_build_storage_plan_uses_date_directory(tmp_path):
    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name="report.pdf",
        file_size=12,
    )

    plan = build_storage_plan(
        storage_root=tmp_path,
        candidate=candidate,
        now=datetime(2026, 5, 6, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    assert plan.target_dir == tmp_path / "2026-05-06"
    assert plan.final_path == tmp_path / "2026-05-06" / "report.pdf"
    assert plan.part_path == tmp_path / "2026-05-06" / "report.pdf.part"


def test_build_storage_plan_generates_name_without_original_filename(tmp_path):
    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name=None,
        file_size=12,
    )

    plan = build_storage_plan(storage_root=tmp_path, candidate=candidate)

    assert plan.final_path.name == "file_unique-id"


def test_build_storage_plan_adds_suffix_when_name_exists(tmp_path):
    dated_dir = tmp_path / "2026-05-06"
    dated_dir.mkdir()
    (dated_dir / "report.pdf").write_bytes(b"old")

    candidate = ArchiveCandidate(
        telegram_file_id="file-id",
        telegram_file_unique_id="unique-id",
        original_file_name="report.pdf",
        file_size=12,
    )

    plan = build_storage_plan(
        storage_root=tmp_path,
        candidate=candidate,
        now=datetime(2026, 5, 6, 10, 0),
    )

    assert plan.final_path.name.startswith("report__")
    assert plan.final_path.suffix == ".pdf"
