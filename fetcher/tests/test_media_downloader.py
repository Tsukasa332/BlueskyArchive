from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import pytest

from app.media_downloader import MediaCapacityError, MediaDownloader, MediaFileTooLargeError, blob_cid, blob_cid_from_url
from app.sync import SyncService


def test_blob_cid_from_link_ref():
    assert blob_cid({"ref": {"$link": "bafkreiabc"}}) == "bafkreiabc"


def test_blob_cid_from_string_ref():
    assert blob_cid({"ref": "bafkreidef"}) == "bafkreidef"


def test_blob_cid_from_bsky_cdn_url():
    assert (
        blob_cid_from_url("https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:example/bafkreig123")
        == "bafkreig123"
    )


def test_blob_cid_from_bsky_cdn_url_strips_format_suffix():
    assert (
        blob_cid_from_url("https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:example/bafkreig123@jpeg")
        == "bafkreig123"
    )


def test_blob_cid_from_non_bsky_url_is_none():
    assert blob_cid_from_url("https://example.com/bafkreig123") is None


@pytest.mark.parametrize("cid", ["", "../escape", "folder/cid", r"folder\cid", "baf-cid", "x" * 256])
def test_media_target_rejects_unsafe_or_invalid_cid(tmp_path: Path, cid: str):
    with pytest.raises(ValueError, match="invalid media CID"):
        MediaDownloader._safe_target(tmp_path, cid)


def test_media_target_resolves_to_storage_directory(tmp_path: Path):
    target = MediaDownloader._safe_target(tmp_path, "bafkreisafecid123")
    assert target.parent == tmp_path.resolve()
    assert target.name == "bafkreisafecid123"


def test_media_capacity_rejects_when_minimum_free_space_would_be_crossed(tmp_path: Path, monkeypatch):
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=1000)
    monkeypatch.setattr("app.media_downloader.shutil.disk_usage", lambda path: SimpleNamespace(free=1099))
    with pytest.raises(MediaCapacityError, match="insufficient media storage"):
        downloader._ensure_capacity(incoming_bytes=100)


def test_media_capacity_accepts_exact_minimum_free_space(tmp_path: Path, monkeypatch):
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=1000)
    monkeypatch.setattr("app.media_downloader.shutil.disk_usage", lambda path: SimpleNamespace(free=1100))
    downloader._ensure_capacity(incoming_bytes=100)


def test_sync_does_not_swallow_media_capacity_error():
    class FullDownloader:
        def save_blob(self, did, cid, media_type):
            raise MediaCapacityError("disk floor reached")

    service = SyncService.__new__(SyncService)
    service.save_own_media = True
    service.client = SimpleNamespace(did="did:plc:owner")
    service.media_downloader = FullDownloader()
    service.repo = object()
    post = SimpleNamespace(author_did="did:plc:owner", uri="at://did:plc:owner/app.bsky.feed.post/1")
    record = {"embed": {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": "bafkreiimagecid"}}}]}}
    with pytest.raises(MediaCapacityError, match="disk floor reached"):
        service._save_media_for_post(post, record, {})


class StreamingResponse:
    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    @property
    def content(self):
        raise AssertionError("streaming save must not access response.content")

    def iter_bytes(self, chunk_size=65536):
        assert chunk_size == 65536
        yield from self._chunks


def test_stream_rejects_content_length_over_file_limit_before_writing(tmp_path: Path):
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=0, max_file_bytes=5, max_total_bytes=0)
    target_dir = tmp_path / "images"
    target_dir.mkdir()
    target = target_dir / "bafkreitarget"
    response = StreamingResponse([b"ignored"], {"content-length": "6"})

    with pytest.raises(MediaFileTooLargeError, match="content_length=6"):
        downloader._stream_to_target(response, target)
    assert not target.exists()
    assert list(target_dir.glob("*.part")) == []


def test_stream_without_content_length_stops_at_actual_file_limit_and_cleans_temp(tmp_path: Path):
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=0, max_file_bytes=5, max_total_bytes=0)
    target_dir = tmp_path / "videos"
    target_dir.mkdir()
    target = target_dir / "bafkreitarget"
    response = StreamingResponse([b"abc", b"def"])

    with pytest.raises(MediaFileTooLargeError, match="received=6"):
        downloader._stream_to_target(response, target)
    assert not target.exists()
    assert list(target_dir.glob("*.part")) == []


def test_stream_with_underreported_content_length_still_enforces_actual_file_limit(tmp_path: Path):
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=0, max_file_bytes=5, max_total_bytes=0)
    target_dir = tmp_path / "images"
    target_dir.mkdir()
    target = target_dir / "bafkreitarget"
    response = StreamingResponse([b"abc", b"def"], {"content-length": "3"})

    with pytest.raises(MediaFileTooLargeError, match="received=6"):
        downloader._stream_to_target(response, target)
    assert not target.exists()
    assert list(target_dir.glob("*.part")) == []


def test_stream_rejects_media_total_limit(tmp_path: Path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "bafkreiexisting").write_bytes(b"12345678")
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=0, max_file_bytes=100, max_total_bytes=10)
    target = image_dir / "bafkreitarget"
    response = StreamingResponse([b"abc"], {"content-length": "3"})

    with pytest.raises(MediaCapacityError, match="maximum_total=10"):
        downloader._stream_to_target(response, target)
    assert not target.exists()


def test_save_blob_streams_to_atomic_target_without_response_content(tmp_path: Path):
    response = StreamingResponse([b"abc", b"def"], {"content-length": "6", "content-type": "video/mp4"})

    class Client:
        @contextmanager
        def stream_blob(self, did, cid):
            yield response

    downloader = MediaDownloader(str(tmp_path), Client(), min_free_bytes=0, max_file_bytes=100, max_total_bytes=1000)
    path, mime_type, size = downloader.save_blob("did:plc:owner", "bafkreivideo123", "video")

    assert path == "videos/bafkreivideo123"
    assert mime_type == "video/mp4"
    assert size == 6
    assert (tmp_path / path).read_bytes() == b"abcdef"
    assert list((tmp_path / "videos").glob("*.part")) == []
    assert downloader._cached_total_bytes == 6


def test_save_caption_blob_uses_caption_directory(tmp_path: Path):
    response = StreamingResponse([b"WEBVTT\n"], {"content-type": "text/vtt"})

    class Client:
        @contextmanager
        def stream_blob(self, did, cid):
            yield response

    downloader = MediaDownloader(str(tmp_path), Client(), min_free_bytes=0)
    path, mime_type, size = downloader.save_blob("did:plc:owner", "bafcaption123", "caption")

    assert path == "captions/bafcaption123"
    assert mime_type == "text/vtt"
    assert size == 7


def test_media_total_cache_can_be_forced_to_rescan(tmp_path: Path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "bafkreione").write_bytes(b"123")
    downloader = MediaDownloader(str(tmp_path), object(), min_free_bytes=0, total_scan_interval_seconds=300)
    assert downloader._media_total_bytes() == 3

    (image_dir / "bafkreitwo").write_bytes(b"4567")
    assert downloader._media_total_bytes() == 3
    assert downloader._media_total_bytes(force=True) == 7
