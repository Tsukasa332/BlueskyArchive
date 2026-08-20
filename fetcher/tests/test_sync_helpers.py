from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.sync import SyncService


def service_without_dependencies() -> SyncService:
    service = SyncService.__new__(SyncService)
    service.full_reconcile_interval = timedelta(days=1)
    return service


def test_boundary_record_missing_after_scan_passes_saved_rkey():
    records = [
        {"uri": "at://did:plc:owner/app.bsky.feed.post/3older"},
        {"uri": "at://did:plc:owner/app.bsky.feed.post/3oldest"},
    ]

    assert SyncService._boundary_record_missing(records, "3target")


def test_boundary_record_is_not_missing_when_present_or_not_reached():
    present = [{"uri": "at://did:plc:owner/app.bsky.feed.post/3target"}]
    newer = [{"uri": "at://did:plc:owner/app.bsky.feed.post/3zzzzz"}]

    assert not SyncService._boundary_record_missing(present, "3target")
    assert not SyncService._boundary_record_missing(newer, "3target")


def test_direct_images_does_not_descend_into_quoted_record():
    embed = {
        "$type": "app.bsky.embed.record#view",
        "record": {"embeds": [{"images": [{"cid": "quoted"}]}]},
    }
    assert list(SyncService._direct_media_embed(embed).get("images") or []) == []


def test_record_with_media_selects_only_direct_media():
    embed = {
        "$type": "app.bsky.embed.recordWithMedia#view",
        "record": {"embeds": [{"images": [{"cid": "quoted"}]}]},
        "media": {"$type": "app.bsky.embed.images#view", "images": [{"cid": "direct"}]},
    }
    assert SyncService._direct_media_embed(embed)["images"][0]["cid"] == "direct"


def test_iter_images_keeps_all_ten_direct_images():
    service = service_without_dependencies()
    images = [{"cid": f"image-{index}"} for index in range(10)]
    record = {"embed": {"$type": "app.bsky.embed.images", "images": images}}
    assert list(service._iter_images(record, {})) == images


def test_iter_images_keeps_all_five_gallery_images_from_record_and_view():
    service = service_without_dependencies()
    record_images = [
        {"$type": "app.bsky.embed.gallery#image", "image": {"ref": {"$link": f"record-{index}"}}}
        for index in range(5)
    ]
    view_images = [
        {
            "$type": "app.bsky.embed.gallery#viewImage",
            "fullsize": f"https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:test/view-{index}",
            "thumbnail": f"https://cdn.bsky.app/img/feed_thumbnail/plain/did:plc:test/view-{index}",
        }
        for index in range(5)
    ]
    record = {"embed": {"$type": "app.bsky.embed.gallery", "items": record_images}}
    view = {"embed": {"$type": "app.bsky.embed.gallery#view", "items": view_images}}

    assert list(service._iter_images(record, {})) == record_images
    assert list(service._iter_images({}, view)) == view_images


def test_gallery_ignores_future_non_image_items():
    service = service_without_dependencies()
    image = {"$type": "app.bsky.embed.gallery#image", "image": {"ref": {"$link": "image-cid"}}}
    video = {"$type": "app.bsky.embed.gallery#video", "video": {"ref": {"$link": "video-cid"}}}
    record = {"embed": {"$type": "app.bsky.embed.gallery", "items": [image, video]}}

    assert list(service._iter_images(record, {})) == [image]
    assert list(service._iter_videos(record, {})) == [video]


def test_save_video_captions_persists_vtt_metadata():
    saved = []

    class Downloader:
        def save_blob(self, did, cid, media_type):
            assert (did, cid, media_type) == ("did:plc:owner", "bafcaption", "caption")
            return "captions/bafcaption", "text/vtt", 42

    class Repo:
        def replace_media_captions(self, asset, captions):
            saved.append((asset, captions))

    service = service_without_dependencies()
    service.media_downloader = Downloader()
    service.repo = Repo()
    asset = SimpleNamespace(id=1)
    service._save_captions(
        "did:plc:owner",
        asset,
        {
            "captions": [{
                "lang": "ja",
                "file": {"ref": {"$link": "bafcaption"}},
            }]
        },
        "at://did:plc:owner/app.bsky.feed.post/test",
    )

    assert saved == [(
        asset,
        [{
            "lang": "ja",
            "cid": "bafcaption",
            "path": "captions/bafcaption",
            "mime_type": "text/vtt",
            "size_bytes": 42,
        }],
    )]


def test_media_storage_disabled_does_not_download_own_media():
    class Downloader:
        def save_blob(self, *args, **kwargs):
            raise AssertionError("media saving is disabled")

    class Repo:
        def replace_post_media_links(self, *args, **kwargs):
            raise AssertionError("disabled storage must not alter existing media links")

    service = service_without_dependencies()
    service.save_own_media = False
    service.client = SimpleNamespace(did="did:plc:owner")
    service.media_downloader = Downloader()
    service.repo = Repo()
    post = SimpleNamespace(author_did="did:plc:owner", uri="at://did:plc:owner/app.bsky.feed.post/test")
    record = {"embed": {"images": [{"image": {"ref": {"$link": "bafimage"}}}]}}

    service._save_media_for_post(post, record, {})


def test_media_storage_never_downloads_another_actors_media():
    class Downloader:
        def save_blob(self, *args, **kwargs):
            raise AssertionError("another actor's media must not be downloaded")

    service = service_without_dependencies()
    service.save_own_media = True
    service.client = SimpleNamespace(did="did:plc:owner")
    service.media_downloader = Downloader()
    service.repo = SimpleNamespace()
    post = SimpleNamespace(author_did="did:plc:other", uri="at://did:plc:other/app.bsky.feed.post/test")
    record = {"embed": {"images": [{"image": {"ref": {"$link": "bafimage"}}}]}}

    service._save_media_for_post(post, record, {})


def test_enabled_media_storage_saves_own_direct_attachment():
    saved = []

    class Downloader:
        def save_blob(self, did, cid, media_type):
            assert (did, cid, media_type) == ("did:plc:owner", "bafimage", "image")
            return "images/bafimage", "image/jpeg", 123

    class Repo:
        def upsert_media_asset(self, **kwargs):
            saved.append(kwargs)

        def replace_post_media_links(self, post, cids):
            assert cids == {"bafimage"}

    service = service_without_dependencies()
    service.save_own_media = True
    service.client = SimpleNamespace(did="did:plc:owner")
    service.media_downloader = Downloader()
    service.repo = Repo()
    post = SimpleNamespace(author_did="did:plc:owner", uri="at://did:plc:owner/app.bsky.feed.post/test")
    record = {"embed": {"images": [{"image": {"ref": {"$link": "bafimage"}}}]}}

    service._save_media_for_post(post, record, {})

    assert saved[0]["post"] is post
    assert saved[0]["cid"] == "bafimage"


def test_full_scan_is_due_after_interval():
    service = service_without_dependencies()
    now = datetime.now(timezone.utc)
    metadata = {"newest_rkey": "3abc", "last_full_reconcile_at": (now - timedelta(days=2)).isoformat()}
    assert service._full_scan_required(metadata, now)


def test_full_scan_not_due_with_recent_reconciliation():
    service = service_without_dependencies()
    now = datetime.now(timezone.utc)
    metadata = {"newest_rkey": "3abc", "last_full_reconcile_at": now.isoformat()}
    assert not service._full_scan_required(metadata, now)
