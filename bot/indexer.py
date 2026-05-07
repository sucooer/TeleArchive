from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def append_index_record(index_file: Path, record: dict) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with index_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def count_records_for_day(index_file: Path, target_day: date) -> int:
    if not index_file.exists():
        return 0

    count = 0
    with index_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            downloaded_at = str(record.get("downloaded_at", ""))
            if downloaded_at.startswith(target_day.isoformat()):
                count += 1
    return count
