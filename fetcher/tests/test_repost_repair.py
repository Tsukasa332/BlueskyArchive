from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.repository import ArchiveRepository
from app.sync import SyncService


def test_missing_repost_subject_waits_for_daily_retry():
    repost = SimpleNamespace(raw_view_json={
        "subject_view_status": "missing",
        "subject_view_attempted_at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(),
    })
    assert not ArchiveRepository._repost_needs_subject_view(repost, retry_after_seconds=900)
    repost.raw_view_json["subject_view_attempted_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert ArchiveRepository._repost_needs_subject_view(repost, retry_after_seconds=900)


def test_incomplete_repost_subject_uses_normal_retry_interval():
    repost = SimpleNamespace(raw_view_json={
        "subject_view_status": "incomplete",
        "subject_view_attempted_at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(),
    })
    assert ArchiveRepository._repost_needs_subject_view(repost, retry_after_seconds=900)


def test_repair_updates_only_repost_and_never_inserts_subject_post():
    record_item = {
        "uri": "at://did:plc:owner/app.bsky.feed.repost/repost1",
        "cid": "repost-cid",
        "value": {"subject": {"uri": "at://did:plc:other/app.bsky.feed.post/post1"}},
    }
    repost = SimpleNamespace(
        uri=record_item["uri"],
        cid=record_item["cid"],
        subject_uri=record_item["value"]["subject"]["uri"],
        raw_record_json=record_item["value"],
        raw_view_json={"record_item": record_item, "subject_view_status": "missing"},
    )
    calls = []

    class Repo:
        def reposts_for_subject_repair(self, *args, **kwargs):
            return [repost]

        def upsert_repost(self, item, subject_view, status):
            calls.append((item, subject_view, status))

    class Session:
        def commit(self):
            pass

    subject_view = {"uri": repost.subject_uri, "author": {"did": "did:plc:other"}, "record": {"text": "restored"}}
    service = SyncService.__new__(SyncService)
    service.repo = Repo()
    service.session = Session()
    service._load_post_views = lambda uris: {repost.subject_uri: subject_view}
    service.media_downloader = SimpleNamespace(
        save_blob=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("repost subject media must not be downloaded")
        )
    )

    assert service.repair_repost_subjects([repost.subject_uri], force=True) == 1
    assert calls == [(record_item, subject_view, "ok")]
    assert not hasattr(service.repo, "upsert_post")


def test_repair_marks_nonempty_record_without_text_as_incomplete():
    repost = SimpleNamespace(
        uri="at://did:plc:owner/app.bsky.feed.repost/repost2",
        cid="repost-cid",
        subject_uri="at://did:plc:other/app.bsky.feed.post/post2",
        raw_record_json={"subject": {"uri": "at://did:plc:other/app.bsky.feed.post/post2"}},
        raw_view_json={},
    )
    statuses = []

    class Repo:
        def reposts_for_subject_repair(self, *args, **kwargs):
            return [repost]

        def upsert_repost(self, item, subject_view, status):
            statuses.append(status)

    class Session:
        def commit(self):
            pass

    service = SyncService.__new__(SyncService)
    service.repo = Repo()
    service.session = Session()
    service._load_post_views = lambda uris: {
        repost.subject_uri: {"author": {"did": "did:plc:other"}, "record": {"$type": "app.bsky.feed.post"}}
    }
    assert service.repair_repost_subjects([repost.subject_uri], force=True) == 1
    assert statuses == ["incomplete"]


def test_repost_full_reconciliation_returns_deleted_count():
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    state = SimpleNamespace(
        cursor=None,
        metadata_json={"newest_rkey": "3old", "last_full_reconcile_at": old},
        last_seen_indexed_at=None,
    )

    class Repo:
        def reposts_for_subject_repair(self, *args, **kwargs):
            return []

        def get_state(self, source):
            return state

        def checkpoint_state(self, source, cursor, metadata):
            state.cursor = cursor
            state.metadata_json = metadata

        def reposts_needing_refresh(self, records, seen_at):
            return records

        def mark_reposts_not_seen_since(self, **kwargs):
            return 2

        def mark_state_success(self, source, cursor, last_seen):
            pass

    class Session:
        def commit(self):
            pass

    class Client:
        did = "did:plc:owner"

        def list_records(self, *args, **kwargs):
            return {"records": []}

    service = SyncService.__new__(SyncService)
    service.repo = Repo()
    service.session = Session()
    service.client = Client()
    service.full_reconcile_interval = timedelta(days=1)
    service.page_limit = 100

    assert service._sync_reposts() == (0, 0, 0, 2)
