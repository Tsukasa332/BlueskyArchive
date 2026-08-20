import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from app.api.presenters import actor_for_did, local_media_url, media_cids_from_view, media_from_view


VIDEO_CID = "bafkreivideocid"
THUMBNAIL = "https://cdn.bsky.app/img/feed_thumbnail/plain/did:plc:test/thumb@jpeg"


class CachedMediaSession:
    def __init__(self):
        self.info = {
            "media_cache": {
                VIDEO_CID: SimpleNamespace(path=f"videos/{VIDEO_CID}"),
            }
        }

    def scalar(self, statement):
        raise AssertionError("preloaded video CID should avoid a database fallback query")


class MissingRecordSession:
    def __init__(self):
        self.info = {}
        self.scalar_calls = 0

    def scalar(self, statement):
        self.scalar_calls += 1
        return None


def test_repost_video_cid_is_collected_for_media_cache():
    view = {
        "embed": {
            "$type": "app.bsky.embed.video#view",
            "cid": VIDEO_CID,
            "playlist": "https://video.bsky.app/watch/test/playlist.m3u8",
            "thumbnail": THUMBNAIL,
        }
    }
    assert media_cids_from_view(view) == {VIDEO_CID}


def test_record_with_media_video_cid_is_collected():
    view = {
        "embed": {
            "$type": "app.bsky.embed.recordWithMedia#view",
            "record": {},
            "media": {"$type": "app.bsky.embed.video#view", "cid": VIDEO_CID, "playlist": "https://video.bsky.app/test.m3u8"},
        }
    }
    assert media_cids_from_view(view) == {VIDEO_CID}


def test_repost_gallery_images_are_collected_and_keep_thumbnail_urls():
    cids = [f"bafkreigallery{index}" for index in range(5)]
    view = {
        "embed": {
            "$type": "app.bsky.embed.gallery#view",
            "items": [
                {
                    "$type": "app.bsky.embed.gallery#viewImage",
                    "fullsize": f"https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:test/{cid}",
                    "thumbnail": f"https://cdn.bsky.app/img/feed_thumbnail/plain/did:plc:test/{cid}",
                    "alt": f"image {index}",
                }
                for index, cid in enumerate(cids)
            ],
        }
    }
    session = MissingRecordSession()

    assert media_cids_from_view(view) == set(cids)
    media = media_from_view(session, view)
    assert len(media) == 5
    assert media[0]["thumb"].endswith(cids[0])
    assert media[0]["alt_text"] == "image 0"


def test_repost_gallery_ignores_non_image_items():
    view = {
        "embed": {
            "$type": "app.bsky.embed.gallery#view",
            "items": [
                {"$type": "app.bsky.embed.gallery#viewImage", "fullsize": "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:test/bafkreiimage"},
                {"$type": "app.bsky.embed.gallery#viewVideo", "playlist": "https://video.bsky.app/example.m3u8"},
            ],
        }
    }

    assert media_cids_from_view(view) == {"bafkreiimage"}


def test_repost_video_uses_local_file_but_keeps_image_thumbnail_as_poster():
    view = {
        "embed": {
            "$type": "app.bsky.embed.video#view",
            "cid": VIDEO_CID,
            "playlist": "https://video.bsky.app/watch/test/playlist.m3u8",
            "thumbnail": THUMBNAIL,
        }
    }
    media = media_from_view(CachedMediaSession(), view)
    assert media == [{
        "url": f"/media/videos/{VIDEO_CID}",
        "thumb": THUMBNAIL,
        "alt_text": None,
        "media_type": "video",
        "presentation": "default",
        "captions": [],
    }]


def test_missing_actor_is_negatively_cached():
    session = MissingRecordSession()
    assert actor_for_did(session, "did:plc:missing") is None
    assert actor_for_did(session, "did:plc:missing") is None
    assert session.scalar_calls == 1


def test_missing_media_is_negatively_cached():
    session = MissingRecordSession()
    assert local_media_url(session, "bafkreimissing") is None
    assert local_media_url(session, "bafkreimissing") is None
    assert session.scalar_calls == 1


def test_nginx_serves_extensionless_video_cids_as_mp4():
    config = (Path(__file__).parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
    video_location = config.split("location /media/videos/", 1)[1].split("location /media/", 1)[0]
    assert "default_type video/mp4;" in video_location
    assert "X-Content-Type-Options \"nosniff\"" in video_location


def test_nginx_media_locations_repeat_security_headers():
    config = (Path(__file__).parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
    video_location = config.split("location /media/videos/", 1)[1].split("location /media/", 1)[0]
    media_location = config.split("location /media/", 1)[1].split("location /", 1)[0]
    for location in (video_location, media_location):
        assert 'Cache-Control "private, max-age=31536000, immutable"' in location
        assert 'Cache-Control "public,' not in location
        assert "Content-Security-Policy" in location
        assert "X-Content-Type-Options \"nosniff\"" in location
        assert "Referrer-Policy \"same-origin\"" in location
        assert "Permissions-Policy" in location


def test_nginx_rate_limits_api_and_manual_sync_posts():
    config = (Path(__file__).parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
    assert "zone=api_per_ip:10m rate=10r/s" in config
    assert "zone=manual_sync_per_ip:1m rate=6r/m" in config
    assert "location = /api/sync" in config
    sync_location = config.split("location = /api/sync", 1)[1].split("location /media/videos/", 1)[0]
    assert "limit_req zone=api_per_ip" in sync_location
    assert "limit_req zone=manual_sync_per_ip" in sync_location
    assert "limit_req_status 429" in sync_location
