from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from bot.types import ArchiveCandidate, StoragePlan


def build_storage_plan(
    storage_root: Path,
    candidate: ArchiveCandidate,
    now: datetime | None = None,
) -> StoragePlan:
    current_time = now or datetime.now().astimezone()
    target_dir = storage_root / current_time.strftime("%Y-%m-%d")
    base_name = candidate.original_file_name or f"file_{candidate.telegram_file_unique_id}"

    final_path = target_dir / base_name
    if final_path.exists():
        suffix = "".join(final_path.suffixes)
        stem = final_path.name[: -len(suffix)] if suffix else final_path.name
        final_path = target_dir / f"{stem}__{secrets.token_hex(3)}{suffix}"

    return StoragePlan(
        target_dir=target_dir,
        final_path=final_path,
        part_path=target_dir / f"{final_path.name}.part",
    )
