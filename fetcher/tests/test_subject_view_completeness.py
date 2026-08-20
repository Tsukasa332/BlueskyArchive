from types import SimpleNamespace

from app.repository import ArchiveRepository, subject_view_complete


def test_subject_view_requires_text_key_not_merely_nonempty_record():
    incomplete = {
        "author": {"did": "did:plc:other"},
        "record": {"$type": "app.bsky.feed.post", "createdAt": "2026-07-11T00:00:00Z"},
    }
    assert not subject_view_complete(incomplete)
    repost = SimpleNamespace(raw_view_json={"subject_view_status": "ok", "subject_view": incomplete})
    assert ArchiveRepository._repost_needs_subject_view(repost, retry_after_seconds=86400)


def test_subject_view_accepts_legitimate_empty_text():
    view = {
        "author": {"did": "did:plc:other"},
        "record": {"$type": "app.bsky.feed.post", "text": ""},
    }
    assert subject_view_complete(view)
