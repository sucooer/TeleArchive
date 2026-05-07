import asyncio

import pytest

from bot.downloader import DownloadCancelled, stream_download_to_path


class FakeResponse:
    def __init__(self, chunks, raise_on_chunk=None):
        self._chunks = chunks
        self._raise_on_chunk = raise_on_chunk

    def raise_for_status(self):
        return None

    async def aiter_bytes(self, chunk_size=None):
        _ = chunk_size
        for index, chunk in enumerate(self._chunks):
            if self._raise_on_chunk == index:
                raise RuntimeError("network broke")
            yield chunk


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    def __init__(self, response):
        self.response = response

    def stream(self, method, url):
        assert method == "GET"
        assert url == "https://example.test/file"
        return FakeStreamContext(self.response)


@pytest.mark.asyncio
async def test_stream_download_to_path_writes_chunks_and_renames(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"]))

    written = await stream_download_to_path(
        client=client,
        url="https://example.test/file",
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
    )

    assert written == 6
    assert final_path.read_bytes() == b"abcdef"
    assert not part_path.exists()


@pytest.mark.asyncio
async def test_stream_download_to_path_removes_part_file_on_failure(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"], raise_on_chunk=1))

    with pytest.raises(RuntimeError, match="network broke"):
        await stream_download_to_path(
            client=client,
            url="https://example.test/file",
            part_path=part_path,
            final_path=final_path,
            chunk_size=3,
        )

    assert not part_path.exists()
    assert not final_path.exists()


@pytest.mark.asyncio
async def test_stream_download_to_path_copies_local_file_source(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    final_path = tmp_path / "report.bin"
    part_path = tmp_path / "report.bin.part"

    written = await stream_download_to_path(
        client=None,
        url=str(source_path),
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
    )

    assert written == 6
    assert final_path.read_bytes() == b"abcdef"
    assert not part_path.exists()


@pytest.mark.asyncio
async def test_stream_download_to_path_reports_progress_for_http_download(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"]))
    progress_updates = []

    async def progress_callback(downloaded_bytes):
        progress_updates.append(downloaded_bytes)

    await stream_download_to_path(
        client=client,
        url="https://example.test/file",
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
        progress_callback=progress_callback,
    )

    assert progress_updates == [3, 6]


@pytest.mark.asyncio
async def test_stream_download_to_path_reports_progress_for_local_copy(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    final_path = tmp_path / "report.bin"
    part_path = tmp_path / "report.bin.part"
    progress_updates = []

    async def progress_callback(downloaded_bytes):
        progress_updates.append(downloaded_bytes)

    await stream_download_to_path(
        client=None,
        url=str(source_path),
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
        progress_callback=progress_callback,
    )

    assert progress_updates == [3, 6]


@pytest.mark.asyncio
async def test_stream_download_to_path_yields_control_during_local_copy(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    final_path = tmp_path / "report.bin"
    part_path = tmp_path / "report.bin.part"
    ticks = []

    async def marker():
        ticks.append("marker")

    task = asyncio.create_task(marker())
    await stream_download_to_path(
        client=None,
        url=str(source_path),
        part_path=part_path,
        final_path=final_path,
        chunk_size=1,
    )
    await task

    assert ticks == ["marker"]


@pytest.mark.asyncio
async def test_stream_download_to_path_stops_when_cancelled_and_removes_part_file(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"]))
    checks = iter([False, True])

    with pytest.raises(DownloadCancelled):
        await stream_download_to_path(
            client=client,
            url="https://example.test/file",
            part_path=part_path,
            final_path=final_path,
            chunk_size=3,
            is_cancelled=lambda: next(checks),
        )

    assert not part_path.exists()
    assert not final_path.exists()


@pytest.mark.asyncio
async def test_download_cancelled_exception_contains_written_bytes(tmp_path):
    final_path = tmp_path / "report.pdf"
    part_path = tmp_path / "report.pdf.part"
    client = FakeClient(FakeResponse([b"abc", b"def"]))
    checks = iter([False, True])

    with pytest.raises(DownloadCancelled) as exc_info:
        await stream_download_to_path(
            client=client,
            url="https://example.test/file",
            part_path=part_path,
            final_path=final_path,
            chunk_size=3,
            is_cancelled=lambda: next(checks),
        )

    assert exc_info.value.bytes_written == 3


@pytest.mark.asyncio
async def test_stream_download_to_path_reports_prepare_progress_for_local_source(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"")
    final_path = tmp_path / "report.bin"
    part_path = tmp_path / "report.bin.part"
    prepare_updates = []

    async def grow_source():
        await asyncio.sleep(0.1)
        source_path.write_bytes(b"abc")
        await asyncio.sleep(0.6)
        source_path.write_bytes(b"abcdef")

    async def prepare_callback(downloaded_bytes):
        prepare_updates.append(downloaded_bytes)

    grow_task = asyncio.create_task(grow_source())
    written = await stream_download_to_path(
        client=None,
        url=str(source_path),
        part_path=part_path,
        final_path=final_path,
        chunk_size=3,
        prepare_callback=prepare_callback,
        expected_size=6,
    )
    await grow_task

    assert written == 6
    assert prepare_updates[-1] == 6
