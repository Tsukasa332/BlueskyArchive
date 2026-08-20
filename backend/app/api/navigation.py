from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session, selectinload

from archive.db.models import Actor, Hashtag, Post, PostMedia, Repost, RepostHashtag
from app.api.presenters import actor_out, post_out, prime_post_context
from app.api.query_helpers import TimelineOrder, reply_parent_did, timeline_ordering
from app.db.session import get_db
from app.schemas.navigation import SidebarNavigationOut

router = APIRouter()


@router.get("/navigation", response_model=SidebarNavigationOut)
def sidebar_navigation(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    target_did = reply_parent_did()
    reply_count = func.count(Post.id)
    friend_rows = db.execute(
        select(target_did.label("did"), reply_count.label("count"))
        .where(Post.deleted.is_(False), Post.reply_parent_uri.startswith("at://"))
        .group_by(target_did)
        .order_by(reply_count.desc(), target_did.asc())
        .limit(limit)
    ).all()

    dids = [row.did for row in friend_rows if row.did]
    actors = db.scalars(select(Actor).where(Actor.did.in_(dids))).all() if dids else []
    actor_by_did = {actor.did: actor for actor in actors}
    self_dids = set(
        db.scalars(select(Post.author_did).where(Post.author_did.in_(dids)).distinct()).all()
    ) if dids else set()
    friends = []
    for row in friend_rows:
        if not row.did:
            continue
        actor = actor_by_did.get(row.did)
        friends.append(
            {
                "actor": actor_out(db, actor) if actor else {"did": row.did},
                "count": row.count,
                "is_self": row.did in self_dids,
            }
        )

    post_tags = (
        select(
            func.lower(Hashtag.tag).label("tag"),
            func.count(func.distinct(Hashtag.post_id)).label("count"),
        )
        .join(Post, Post.id == Hashtag.post_id)
        .where(Post.deleted.is_(False))
        .group_by(func.lower(Hashtag.tag))
    )
    repost_tags = (
        select(
            func.lower(RepostHashtag.tag).label("tag"),
            func.count(func.distinct(RepostHashtag.repost_id)).label("count"),
        )
        .join(Repost, Repost.id == RepostHashtag.repost_id)
        .where(Repost.deleted.is_(False))
        .group_by(func.lower(RepostHashtag.tag))
    )
    combined_tags = union_all(post_tags, repost_tags).subquery()
    total_count = func.sum(combined_tags.c.count)
    hashtag_rows = db.execute(
        select(combined_tags.c.tag, total_count.label("count"))
        .where(combined_tags.c.tag.is_not(None), combined_tags.c.tag != "")
        .group_by(combined_tags.c.tag)
        .order_by(total_count.desc(), combined_tags.c.tag.asc())
        .limit(limit)
    ).all()

    return {
        "friends": friends,
        "hashtags": [{"tag": row.tag, "count": row.count} for row in hashtag_rows],
    }


@router.get("/timeline/replies")
def reply_timeline(
    reply_to: str = Query(min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    target_did = reply_parent_did()
    stmt = (
        select(Post)
        .where(target_did == reply_to)
        .options(
            selectinload(Post.author),
            selectinload(Post.media_links).selectinload(PostMedia.media_asset),
            selectinload(Post.external_links),
        )
    )
    count_stmt = select(func.count()).select_from(Post).where(target_did == reply_to)
    if not include_deleted:
        stmt = stmt.where(Post.deleted.is_(False))
        count_stmt = count_stmt.where(Post.deleted.is_(False))
    ordering = timeline_ordering(Post.record_created_at, Post.indexed_at, order, Post.id)
    posts = list(db.scalars(stmt.order_by(*ordering).limit(limit).offset(offset)).all())
    prime_post_context(db, posts)
    return {
        "items": [{"kind": "post", "post": post_out(post, db)} for post in posts],
        "total": db.scalar(count_stmt) or 0,
        "limit": limit,
        "offset": offset,
    }
