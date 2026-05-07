from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveCandidate:
    telegram_file_id: str
    telegram_file_unique_id: str
    original_file_name: str | None
    file_size: int | None


@dataclass(frozen=True)
class StoragePlan:
    target_dir: Path
    final_path: Path
    part_path: Path
