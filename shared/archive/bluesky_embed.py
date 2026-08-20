from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

POST_COLLECTION = "app.bsky.feed.post"


def blob_cid(blob: Any) -> str | None:
    if not blob:
        return None
    if isinstance(blob, str):
        return None if blob.startswith(("http://", "https://")) else blob
    if not isinstance(blob, dict):
        return None
    ref = blob.get("ref") or blob.get("$link")
    if isinstance(ref, dict):
        return ref.get("$link")
    if isinstance(ref, str):
        return ref
    return None


def blob_cid_from_url(url: str | None) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc != "cdn.bsky.app":
        return None
    candidate = parsed.path.rstrip("/").rsplit("/", 1)[-1].split("@", 1)[0]
    return candidate if candidate.startswith("baf") else None


def direct_media_embed(embed: Any) -> dict[str, Any]:
    if not isinstance(embed, dict):
        return {}
    if "recordWithMedia" in str(embed.get("$type") or ""):
        media = embed.get("media")
        return media if isinstance(media, dict) else {}
    return embed


def direct_image_items(embed: Any) -> Iterator[dict[str, Any]]:
    media = direct_media_embed(embed)
    items = media.get("images")
    gallery_items = False
    if not isinstance(items, list):
        items = media.get("items")
        gallery_items = True
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("$type") or "").lower()
        if not gallery_items or (
            item.get("image")
            or item.get("fullsize")
            or item.get("thumb")
            or item.get("thumbnail")
            or "image" in item_type
        ):
            yield item


def direct_video_items(embed: Any) -> Iterator[dict[str, Any]]:
    """Yield direct videos, including future video items inside a gallery."""
    media = direct_media_embed(embed)
    items = media.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("$type") or "").lower()
            if (
                item.get("video")
                or item.get("playlist")
                or "video" in item_type
            ):
                yield item
        return
    media_type = str(media.get("$type") or "").lower()
    if (
        media.get("video")
        or media.get("playlist")
        or media.get("thumbnail")
        or "video" in media_type
    ):
        yield media


def embedded_record(embed: Any) -> dict[str, Any]:
    """Return the embedded record payload from record or recordWithMedia."""
    if not isinstance(embed, dict):
        return {}
    record = embed.get("record")
    if not isinstance(record, dict):
        return {}
    nested = record.get("record")
    return nested if isinstance(nested, dict) else record


def embedded_record_ref(*embeds: Any) -> dict[str, str]:
    """Return the first embedded record strong reference found in record/view embeds."""
    for embed in embeds:
        record = embedded_record(embed)
        uri = record.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        ref = {"uri": uri}
        cid = record.get("cid")
        if isinstance(cid, str) and cid:
            ref["cid"] = cid
        return ref
    return {}


def collection_from_at_uri(uri: str | None) -> str | None:
    if not isinstance(uri, str) or not uri.startswith("at://"):
        return None
    parts = uri.split("/")
    return parts[3] if len(parts) > 3 else None


def quote_uri(*embeds: Any) -> str | None:
    uri = embedded_record_ref(*embeds).get("uri")
    return uri if collection_from_at_uri(uri) == POST_COLLECTION else None


def hashtag_rows(record: Any) -> list[dict[str, Any]]:
    """Normalize tags from rich-text facets and the post-level tags property."""
    if not isinstance(record, dict):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(tag: Any, start_byte: Any = None, end_byte: Any = None) -> None:
        if not isinstance(tag, str):
            return
        normalized = tag.strip().removeprefix("#").strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            return
        seen.add(key)
        rows.append({"tag": normalized, "start_byte": start_byte, "end_byte": end_byte})

    for facet in record.get("facets") or []:
        if not isinstance(facet, dict):
            continue
        index = facet.get("index") or {}
        for feature in facet.get("features") or []:
            if isinstance(feature, dict) and str(feature.get("$type") or "").endswith("#tag"):
                append(feature.get("tag"), index.get("byteStart"), index.get("byteEnd"))
    for tag in record.get("tags") or []:
        append(tag)
    return rows


def label_values(record: Any, view: Any = None) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    def append(value: Any) -> None:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            values.append(value)

    if isinstance(record, dict):
        labels = record.get("labels") or {}
        if isinstance(labels, dict):
            for item in labels.get("values") or []:
                if isinstance(item, dict):
                    append(item.get("val"))
    if isinstance(view, dict):
        for item in view.get("labels") or []:
            if isinstance(item, dict):
                append(item.get("val"))
    return values


def video_embed(record_embed: Any, view_embed: Any = None) -> dict[str, Any]:
    """Merge record and view video fields while retaining captions/presentation."""
    result: dict[str, Any] = {}
    for embed in (record_embed, view_embed):
        media = direct_media_embed(embed)
        if not isinstance(media, dict):
            continue
        media_type = str(media.get("$type") or "")
        if media.get("video") or media.get("playlist") or media.get("thumbnail") or "video" in media_type:
            result.update(media)
    return result
