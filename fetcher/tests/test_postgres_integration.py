import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from archive.db.base import Base
from archive.db.models import Actor, Post, Repost
from app.repository import ArchiveRepository
from app.sync import POST_COLLECTION, SyncService


@pytest.fixture()
def postgres_session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL; SQLite is not an integration-test substitute")
    schema = f"test_{uuid4().hex}"
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        Base.metadata.create_all(connection)
        session = Session(connection)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
    engine.dispose()


def test_incremental_sync_stops_at_saved_rkey_boundary(postgres_session):
    repo = ArchiveRepository(postgres_session)
    state = repo.get_state("posts")
    state.metadata_json = {
        "newest_rkey": "3boundary",
        "last_full_reconcile_at": datetime.now(timezone.utc).isoformat(),
    }
    postgres_session.commit()
    records = [
        {"uri": "at://did:plc:owner/app.bsky.feed.post/3new", "cid": "new-cid", "value": {"text": "new", "createdAt": "2026-07-11T00:00:00Z"}},
        {"uri": "at://did:plc:owner/app.bsky.feed.post/3boundary", "cid": "old-cid", "value": {"text": "old", "createdAt": "2026-07-10T00:00:00Z"}},
    ]

    class Client:
        did = "did:plc:owner"

        def list_records(self, collection, **kwargs):
            assert collection == POST_COLLECTION
            return {"records": records}

        def get_posts(self, uris):
            return {"posts": [{"uri": uri, "author": {"did": "did:plc:owner"}, "record": {"text": "new"}} for uri in uris]}

    service = SyncService(postgres_session, Client(), object(), full_reconcile_interval_seconds=86400)
    assert service._sync_posts()[:3] == (1, 1, 0)
    assert list(postgres_session.scalars(select(Post.uri)).all()) == [records[0]["uri"]]


def test_post_and_repost_deletion_reconciliation_uses_database_state(postgres_session):
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    actor = Actor(did="did:plc:owner", raw_json={})
    postgres_session.add(actor)
    postgres_session.flush()
    postgres_session.add(Post(
        uri="at://did:plc:owner/app.bsky.feed.post/old", author_did=actor.did, text="old",
        raw_record_json={}, raw_view_json={}, repo_seen_at=old, deleted=False,
    ))
    postgres_session.add(Repost(
        uri="at://did:plc:owner/app.bsky.feed.repost/old", actor_did=actor.did,
        subject_uri="at://did:plc:other/app.bsky.feed.post/subject", raw_record_json={}, raw_view_json={},
        repo_seen_at=old, deleted=False,
    ))
    postgres_session.flush()
    repo = ArchiveRepository(postgres_session)
    scan_started = datetime.now(timezone.utc)

    assert repo.mark_posts_not_seen_since(author_did=actor.did, scan_started_at=scan_started) == 1
    assert repo.mark_reposts_not_seen_since(actor_did=actor.did, scan_started_at=scan_started) == 1
