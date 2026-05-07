import json
from datetime import date

from bot.indexer import append_index_record, count_records_for_day


def test_append_index_record_creates_parent_directory_and_jsonl(tmp_path):
    index_file = tmp_path / "data" / "index.jsonl"
    record = {"saved_path": "storage/2026-05-06/report.pdf", "file_size": 123}

    append_index_record(index_file=index_file, record=record)

    lines = index_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record


def test_count_records_for_day_reads_matching_dates(tmp_path):
    index_file = tmp_path / "data" / "index.jsonl"
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        "\n".join(
            [
                json.dumps({"downloaded_at": "2026-05-06T10:00:00"}),
                json.dumps({"downloaded_at": "2026-05-06T11:00:00"}),
                json.dumps({"downloaded_at": "2026-05-07T09:00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert count_records_for_day(index_file, date(2026, 5, 6)) == 2
