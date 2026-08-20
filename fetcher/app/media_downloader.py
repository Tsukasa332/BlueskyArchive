from pathlib import Path
import os
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse
from typing import Any

from archive.bluesky_embed import blob_cid, blob_cid_from_url
from app.bluesky_client import BlueskyClient


class MediaCapacityError(RuntimeError):
    pass


class MediaFileTooLargeError(RuntimeError):
    pass


class MediaDownloader:
    def __init__(
        self,
        media_root: str,
        client: BlueskyClient,
        min_free_bytes: int = 5368709120,
        max_file_bytes: int = 157286400,
        max_total_bytes: int = 53687091200,
        total_scan_interval_seconds: int = 300,
    ) -> None:
        self.media_root = Path(media_root)
        self.client = client
        self.min_free_bytes = max(0, min_free_bytes)
        self.max_file_bytes = max(0, max_file_bytes)
        self.max_total_bytes = max(0, max_total_bytes)
        self.total_scan_interval_seconds = max(0, total_scan_interval_seconds)
        self._cached_total_bytes: int | None = None
        self._cached_total_checked_at = 0.0

    def save_blob(self, did: str, cid: str, media_type: str) -> tuple[str, str | None, int]:
        subdir = {"video": "videos", "caption": "captions"}.get(media_type, "images")
        directory = self.media_root / subdir
        directory.mkdir(parents=True, exist_ok=True)
        target = self._safe_target(directory, cid)
        if target.exists() and target.stat().st_size > 0:
            return f"{subdir}/{cid}", None, target.stat().st_size
        with self.client.stream_blob(did, cid) as response:
            mime_type, size = self._stream_to_target(response, target)
        return f"{subdir}/{cid}", mime_type, size

    def save_url(self, url: str | None, cid: str, media_type: str) -> tuple[str, str | None, int]:
        if not isinstance(url, str):
            raise ValueError("media URL must be a string")
        parsed = urlparse(url)
        if parsed.netloc != "cdn.bsky.app":
            raise ValueError("only Bluesky CDN media URLs can be saved")
        subdir = {"video": "videos", "caption": "captions"}.get(media_type, "images")
        directory = self.media_root / subdir
        directory.mkdir(parents=True, exist_ok=True)
        target = self._safe_target(directory, cid)
        if target.exists() and target.stat().st_size > 0:
            return f"{subdir}/{cid}", None, target.stat().st_size
        with self.client.client.stream("GET", url) as response:
            response.raise_for_status()
            mime_type, size = self._stream_to_target(response, target)
        return f"{subdir}/{cid}", mime_type, size

    @staticmethod
    def _safe_target(directory: Path, cid: str) -> Path:
        if not isinstance(cid, str) or not 1 <= len(cid) <= 255 or re.fullmatch(r"[A-Za-z0-9]+", cid) is None:
            raise ValueError("invalid media CID")
        resolved_directory = directory.resolve()
        target = (resolved_directory / cid).resolve()
        if target.parent != resolved_directory:
            raise ValueError("media target escapes its storage directory")
        return target

    def _ensure_capacity(self, incoming_bytes: int = 0) -> None:
        free_bytes = shutil.disk_usage(self.media_root).free
        required_bytes = self.min_free_bytes + max(0, incoming_bytes)
        if free_bytes < required_bytes:
            raise MediaCapacityError(
                f"insufficient media storage free={free_bytes} required={required_bytes} "
                f"minimum_free={self.min_free_bytes} incoming={incoming_bytes}"
            )

    def _ensure_total_capacity(self, current_total_bytes: int, incoming_bytes: int) -> None:
        if self.max_total_bytes and current_total_bytes + incoming_bytes > self.max_total_bytes:
            raise MediaCapacityError(
                f"media storage limit exceeded current={current_total_bytes} incoming={incoming_bytes} "
                f"maximum_total={self.max_total_bytes}"
            )

    def _media_total_bytes(self, *, force: bool = False) -> int:
        now = time.monotonic()
        cache_fresh = (
            self._cached_total_bytes is not None
            and not force
            and now - self._cached_total_checked_at < self.total_scan_interval_seconds
        )
        if cache_fresh:
            return self._cached_total_bytes or 0
        total = 0
        for subdir in ("images", "videos", "captions"):
            directory = self.media_root / subdir
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.name.startswith(".") or not path.is_file():
                    continue
                total += path.stat().st_size
        self._cached_total_bytes = total
        self._cached_total_checked_at = now
        return total

    def _stream_to_target(self, response: Any, target: Path) -> tuple[str | None, int]:
        content_length = self._content_length(response)
        if self.max_file_bytes and content_length is not None and content_length > self.max_file_bytes:
            raise MediaFileTooLargeError(
                f"media response exceeds file limit content_length={content_length} maximum={self.max_file_bytes}"
            )
        current_total = self._media_total_bytes()
        if content_length is not None:
            self._ensure_capacity(content_length)
            self._ensure_total_capacity(current_total, content_length)
        else:
            self._ensure_capacity()

        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
        size = 0
        try:
            os.chmod(temporary, 0o644)
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_bytes(chunk_size=65536):
                    if not chunk:
                        continue
                    next_size = size + len(chunk)
                    if self.max_file_bytes and next_size > self.max_file_bytes:
                        raise MediaFileTooLargeError(
                            f"media stream exceeds file limit received={next_size} maximum={self.max_file_bytes}"
                        )
                    self._ensure_capacity(len(chunk))
                    self._ensure_total_capacity(current_total, next_size)
                    handle.write(chunk)
                    size = next_size
                if size == 0:
                    raise ValueError("refusing to save empty media response")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        self._cached_total_bytes = current_total + size
        self._cached_total_checked_at = time.monotonic()
        return response.headers.get("content-type"), size

    @staticmethod
    def _content_length(response: Any) -> int | None:
        value = response.headers.get("content-length")
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None
