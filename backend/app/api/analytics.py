from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, literal, select, union_all
from sqlalchemy.orm import Session

from archive.db.models import Post, Repost
from app.api.query_helpers import local_created_at, reply_parent_did
from app.core.config import settings
from app.db.session import get_db
from app.schemas.analytics import AnalyticsOut, AnalyticsPeriod

router = APIRouter()


def period_start(period: AnalyticsPeriod, now: datetime | None = None) -> datetime | None:
    if period == "all":
        return None
    current = now or datetime.now(timezone.utc)
    if period == "week":
        return current - timedelta(days=7)
    months = 12 if period == "year" else 1
    target_month = current.month - months
    target_year = current.year
    while target_month <= 0:
        target_month += 12
        target_year -= 1
    target_day = min(current.day, monthrange(target_year, target_month)[1])
    return current.replace(year=target_year, month=target_month, day=target_day)


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    period: AnalyticsPeriod = "all",
    db: Session = Depends(get_db),
):
    start = period_start(period, datetime.now(ZoneInfo(settings.app_timezone)))
    target_did = reply_parent_did()
    reply_to_other = and_(
        Post.reply_parent_uri.startswith("at://"),
        target_did.is_not(None),
        target_did != Post.author_did,
    )
    post_counts = select(
        func.count(Post.id).label("post_count"),
        func.count(Post.id).filter(reply_to_other).label("reply_count"),
    ).where(Post.deleted.is_(False))
    repost_count = select(func.count(Repost.id)).where(Repost.deleted.is_(False))
    if start is not None:
        post_counts = post_counts.where(Post.record_created_at >= start)
        repost_count = repost_count.where(Repost.record_created_at >= start)

    post_count, reply_count = db.execute(post_counts).one()
    reposts = db.scalar(repost_count) or 0
    replies = reply_count or 0
    own_posts = (post_count or 0) - replies

    post_events = select(Post.record_created_at.label("created_at")).where(
        Post.deleted.is_(False),
        Post.record_created_at.is_not(None),
    )
    repost_events = select(Repost.record_created_at.label("created_at")).where(
        Repost.deleted.is_(False),
        Repost.record_created_at.is_not(None),
    )
    if start is not None:
        post_events = post_events.where(Post.record_created_at >= start)
        repost_events = repost_events.where(Repost.record_created_at >= start)
    events = union_all(post_events, repost_events).subquery()
    local_created = local_created_at(events.c.created_at)
    weekday = func.extract("isodow", local_created)
    hour = func.extract("hour", local_created)
    rows = db.execute(
        select(
            weekday.label("weekday"),
            hour.label("hour"),
            func.count(literal(1)).label("count"),
        )
        .group_by(weekday, hour)
        .order_by(weekday, hour)
    ).all()

    return {
        "period": period,
        "start_at": start,
        "counts": {
            "own_posts": own_posts,
            "replies": replies,
            "reposts": reposts,
            "total": own_posts + replies + reposts,
        },
        "heatmap": [
            {"weekday": int(row.weekday), "hour": int(row.hour), "count": row.count}
            for row in rows
        ],
    }
