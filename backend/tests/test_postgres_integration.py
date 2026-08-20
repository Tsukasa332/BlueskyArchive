import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from archive.db.base import Base
from archive.db.models import Actor, Hashtag, Post, Repost, RepostHashtag
from app.api.analytics import analytics
from app.api.navigation import reply_timeline, sidebar_navigation
from app.api.posts import search_timeline_by_tag, timeline
from app.core.config import settings


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


def test_tag_search_is_case_insensitive_exact_and_mixes_posts_with_reposts(postgres_session):
    actor = Actor(did="did:plc:owner", handle="owner.test", raw_json={})
    postgres_session.add(actor)
    postgres_session.flush()
    created_at = datetime.now(timezone.utc)
    post = Post(
        uri="at://did:plc:owner/app.bsky.feed.post/post1", author_did=actor.did, text="#Mixed",
        record_created_at=created_at, raw_record_json={}, raw_view_json={}, deleted=False,
    )
    repost = Repost(
        uri="at://did:plc:owner/app.bsky.feed.repost/repost1", actor_did=actor.did,
        subject_uri="at://did:plc:other/app.bsky.feed.post/subject", record_created_at=created_at,
        raw_record_json={}, raw_view_json={}, deleted=False,
    )
    postgres_session.add_all([post, repost])
    postgres_session.flush()
    postgres_session.add_all([
        Hashtag(post_id=post.id, tag="Mixed"),
        RepostHashtag(repost_id=repost.id, tag="mIxEd"),
    ])
    postgres_session.flush()

    result = search_timeline_by_tag("MIXED", limit=50, offset=0, include_deleted=False, order="desc", db=postgres_session)
    assert result["total"] == 2
    assert {item["kind"] for item in result["items"]} == {"post", "repost"}

    partial = search_timeline_by_tag("mix", limit=50, offset=0, include_deleted=False, order="desc", db=postgres_session)
    assert partial["total"] == 0


def test_timeline_day_ascending_orders_newest_day_first_and_each_day_morning_to_night(postgres_session, monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "Asia/Tokyo")
    actor = Actor(did="did:plc:sort-owner", handle="sort.test", raw_json={})
    postgres_session.add(actor)
    postgres_session.flush()
    events = [
        Post(
            uri=f"at://{actor.did}/app.bsky.feed.post/newer-late",
            author_did=actor.did,
            text="newer late",
            record_created_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
            indexed_at=datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc),
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
        Repost(
            uri=f"at://{actor.did}/app.bsky.feed.repost/newer-early",
            actor_did=actor.did,
            subject_uri="at://did:plc:subject/app.bsky.feed.post/newer-early",
            record_created_at=datetime(2026, 8, 7, 15, 30, tzinfo=timezone.utc),
            indexed_at=datetime(2026, 8, 7, 15, 31, tzinfo=timezone.utc),
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
        Post(
            uri=f"at://{actor.did}/app.bsky.feed.post/older-late",
            author_did=actor.did,
            text="older late",
            record_created_at=datetime(2026, 8, 7, 14, 30, tzinfo=timezone.utc),
            indexed_at=datetime(2026, 8, 7, 14, 31, tzinfo=timezone.utc),
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
        Post(
            uri=f"at://{actor.did}/app.bsky.feed.post/older-early",
            author_did=actor.did,
            text="older early",
            record_created_at=datetime(2026, 8, 6, 16, 0, tzinfo=timezone.utc),
            indexed_at=datetime(2026, 8, 6, 16, 1, tzinfo=timezone.utc),
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
    ]
    postgres_session.add_all(events)
    postgres_session.flush()

    first_page = timeline(
        year=None,
        month=None,
        day=None,
        limit=2,
        offset=0,
        include_deleted=False,
        order="day_asc",
        db=postgres_session,
    )
    second_page = timeline(
        year=None,
        month=None,
        day=None,
        limit=2,
        offset=2,
        include_deleted=False,
        order="day_asc",
        db=postgres_session,
    )

    def item_uri(item):
        value = item[item["kind"]]
        return value["uri"] if isinstance(value, dict) else value.uri

    assert [item_uri(item) for item in first_page["items"]] == [events[1].uri, events[0].uri]
    assert [item_uri(item) for item in second_page["items"]] == [events[3].uri, events[2].uri]


def test_sidebar_navigation_and_reply_filter_use_existing_archive_data(postgres_session):
    owner = Actor(did="did:plc:owner", handle="owner.test", raw_json={})
    alice = Actor(did="did:plc:alice", handle="alice.test", display_name="Alice", raw_json={})
    bob = Actor(did="did:plc:bob", handle="bob.test", display_name="Bob", raw_json={})
    postgres_session.add_all([owner, alice, bob])
    postgres_session.flush()
    created_at = datetime.now(timezone.utc)
    posts = [
        Post(
            uri=f"at://{owner.did}/app.bsky.feed.post/reply{index}",
            author_did=owner.did,
            text="#Mixed",
            reply_parent_uri=f"at://{target}/app.bsky.feed.post/parent{index}",
            record_created_at=created_at,
            raw_record_json={},
            raw_view_json={},
            deleted=deleted,
        )
        for index, (target, deleted) in enumerate(
            [(alice.did, False), (alice.did, False), (bob.did, False), (alice.did, True), (owner.did, False)],
            start=1,
        )
    ]
    repost = Repost(
        uri=f"at://{owner.did}/app.bsky.feed.repost/repost2",
        actor_did=owner.did,
        subject_uri=f"at://{bob.did}/app.bsky.feed.post/subject2",
        record_created_at=created_at,
        raw_record_json={},
        raw_view_json={},
        deleted=False,
    )
    postgres_session.add_all([*posts, repost])
    postgres_session.flush()
    postgres_session.add_all(
        [
            Hashtag(post_id=posts[0].id, tag="Mixed"),
            Hashtag(post_id=posts[0].id, tag="MIXED"),
            Hashtag(post_id=posts[1].id, tag="Other"),
            Hashtag(post_id=posts[3].id, tag="Deleted"),
            RepostHashtag(repost_id=repost.id, tag="mixed"),
        ]
    )
    postgres_session.flush()

    navigation = sidebar_navigation(limit=20, db=postgres_session)
    assert [(item["actor"].did, item["count"]) for item in navigation["friends"]] == [
        (alice.did, 2),
        (bob.did, 1),
        (owner.did, 1),
    ]
    assert [item["is_self"] for item in navigation["friends"]] == [False, False, True]
    assert navigation["hashtags"] == [
        {"tag": "mixed", "count": 2},
        {"tag": "other", "count": 1},
    ]

    replies = reply_timeline(
        reply_to=alice.did,
        limit=50,
        offset=0,
        include_deleted=False,
        order="desc",
        db=postgres_session,
    )
    assert replies["total"] == 2
    assert {item["post"].reply_parent_uri for item in replies["items"]} == {
        f"at://{alice.did}/app.bsky.feed.post/parent1",
        f"at://{alice.did}/app.bsky.feed.post/parent2",
    }


def test_analytics_partitions_posts_and_uses_local_activity_time(postgres_session):
    owner = Actor(did="did:plc:analytics-owner", handle="analytics.test", raw_json={})
    other = Actor(did="did:plc:analytics-other", handle="other.test", raw_json={})
    postgres_session.add_all([owner, other])
    postgres_session.flush()
    created_at = datetime.now(timezone.utc)
    posts = [
        Post(
            uri=f"at://{owner.did}/app.bsky.feed.post/own",
            author_did=owner.did,
            text="own",
            record_created_at=created_at,
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
        Post(
            uri=f"at://{owner.did}/app.bsky.feed.post/reply-other",
            author_did=owner.did,
            text="reply",
            reply_parent_uri=f"at://{other.did}/app.bsky.feed.post/parent",
            record_created_at=created_at,
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
        Post(
            uri=f"at://{owner.did}/app.bsky.feed.post/reply-self",
            author_did=owner.did,
            text="continued",
            reply_parent_uri=f"at://{owner.did}/app.bsky.feed.post/own",
            record_created_at=created_at,
            raw_record_json={},
            raw_view_json={},
            deleted=False,
        ),
    ]
    repost = Repost(
        uri=f"at://{owner.did}/app.bsky.feed.repost/activity",
        actor_did=owner.did,
        subject_uri=f"at://{other.did}/app.bsky.feed.post/subject",
        record_created_at=created_at,
        raw_record_json={},
        raw_view_json={},
        deleted=False,
    )
    postgres_session.add_all([*posts, repost])
    postgres_session.flush()

    result = analytics(period="all", db=postgres_session)

    assert result["counts"] == {
        "own_posts": 2,
        "replies": 1,
        "reposts": 1,
        "total": 4,
    }
    assert sum(cell["count"] for cell in result["heatmap"]) == 4
