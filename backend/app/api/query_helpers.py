from datetime import date, datetime, time, timezone
from typing import Any, Literal, TypeAlias
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, selectinload

from archive.db.models import Post, PostMedia, Repost
from app.api.presenters import post_out, prime_post_context, prime_repost_context, repost_out
from app.core.config import settings

TimelineOrder: TypeAlias = Literal["desc", "day_asc", "asc"]


def reply_parent_did():
    return func.nullif(func.split_part(Post.reply_parent_uri, "/", 3), "")


def date_range(
    year: int | None,
    month: int | None,
    day: int | None,
) -> tuple[datetime, datetime] | None:
    if year is None:
        return None
    app_timezone = ZoneInfo(settings.app_timezone)
    start = datetime.combine(date(year, month or 1, day or 1), time.min, tzinfo=app_timezone)
    if day is not None and month is not None:
        end = datetime.combine(date.fromordinal(date(year, month, day).toordinal() + 1), time.min, tzinfo=app_timezone)
    elif month is not None:
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        end = datetime.combine(date(next_year, next_month, 1), time.min, tzinfo=app_timezone)
    else:
        end = datetime.combine(date(year + 1, 1, 1), time.min, tzinfo=app_timezone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_created_at(column):
    return func.timezone(settings.app_timezone, column)


def timeline_ordering(created_at, indexed_at, order: TimelineOrder, *tie_breakers):
    stable_order = tuple(column.asc() for column in tie_breakers)
    if order == "day_asc":
        local_day = cast(local_created_at(created_at), Date)
        return (
            local_day.desc().nullslast(),
            created_at.asc().nullslast(),
            indexed_at.asc().nullslast(),
            *stable_order,
        )
    if order == "asc":
        return (
            created_at.asc().nullslast(),
            indexed_at.asc().nullslast(),
            *stable_order,
        )
    return (
        created_at.desc().nullslast(),
        indexed_at.desc().nullslast(),
        *stable_order,
    )


def timeline_response(
    db: Session,
    rows: list[Any],
    total: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    post_ids = [row.item_id for row in rows if row.kind == "post"]
    repost_ids = [row.item_id for row in rows if row.kind == "repost"]
    posts = (
        list(
            db.scalars(
                select(Post)
                .where(Post.id.in_(post_ids))
                .options(
                    selectinload(Post.author),
                    selectinload(Post.media_links).selectinload(PostMedia.media_asset),
                    selectinload(Post.external_links),
                )
            ).all()
        )
        if post_ids
        else []
    )
    reposts = list(db.scalars(select(Repost).where(Repost.id.in_(repost_ids))).all()) if repost_ids else []
    prime_post_context(db, posts)
    prime_repost_context(db, reposts)
    post_map = {post.id: post_out(post, db).model_dump(mode="json") for post in posts}
    repost_map = {repost.id: repost_out(repost, db) for repost in reposts}
    items = [
        {"kind": row.kind, row.kind: post_map[row.item_id] if row.kind == "post" else repost_map[row.item_id]}
        for row in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
