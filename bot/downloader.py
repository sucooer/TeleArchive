from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class DownloadCancelled(Exception):
    pass


async def stream_download_to_path(
    client,
    url: str,
    part_path: Path,
    final_path: Path,
    chunk_size: int,
    progress_callback=None,
    is_cancelled=None,
) -> int:
    bytes_written = 0
    part_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        source_path = Path(url)
        if source_path.is_file():
            with source_path.open("rb") as source, part_path.open("wb") as target:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise DownloadCancelled()
                    chunk = source.read(chunk_size)
                    if not chunk:
                        break
                    target.write(chunk)
                    bytes_written += len(chunk)
                    if progress_callback is not None:
                        await progress_callback(bytes_written)
                    # Yield so callback queries and message edits can be processed during long local copies.
                    await asyncio.sleep(0)
            bytes_written = part_path.stat().st_size
            part_path.replace(final_path)
            return bytes_written

        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with part_path.open("wb") as handle:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    if is_cancelled is not None and is_cancelled():
                        raise DownloadCancelled()
                    if not chunk:
                        continue
                    handle.write(chunk)
                    bytes_written += len(chunk)
                    if progress_callback is not None:
                        await progress_callback(bytes_written)
                    await asyncio.sleep(0)
        part_path.replace(final_path)
        return bytes_written
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise
