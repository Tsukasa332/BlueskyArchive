from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import Date, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, selectinload

from archive.db.models import Hashtag, Mention, Post, PostMedia, Repost, RepostHashtag, SyncRun, SyncState
from app.api.presenters import post_out, prime_post_context, prime_repost_context, repost_out
from app.api.query_helpers import TimelineOrder, date_range, local_created_at, timeline_ordering, timeline_response
from app.db.session import get_db
from app.schemas.posts import CalendarOut, PostDetailOut, PostListOut, RepostListOut

router = APIRouter()


@router.get("/posts", response_model=PostListOut)
def list_posts(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    day: int | None = Query(default=None, ge=1, le=31),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    stmt = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.media_links).selectinload(PostMedia.media_asset),
        selectinload(Post.external_links),
    )
    count_stmt = select(func.count()).select_from(Post)
    if not include_deleted:
        stmt = stmt.where(Post.deleted.is_(False))
        count_stmt = count_stmt.where(Post.deleted.is_(False))
    selected_range = date_range(year, month, day)
    if selected_range:
        start, end = selected_range
        stmt = stmt.where(Post.record_created_at >= start, Post.record_created_at < end)
        count_stmt = count_stmt.where(Post.record_created_at >= start, Post.record_created_at < end)
    ordering = timeline_ordering(Post.record_created_at, Post.indexed_at, order, Post.id)
    posts = list(db.scalars(stmt.order_by(*ordering).limit(limit).offset(offset)).all())
    prime_post_context(db, posts)
    return {"items": [post_out(post, db) for post in posts], "total": db.scalar(count_stmt) or 0}


@router.get("/reposts", response_model=RepostListOut)
def list_reposts(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    day: int | None = Query(default=None, ge=1, le=31),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    stmt = select(Repost)
    count_stmt = select(func.count()).select_from(Repost)
    if not include_deleted:
        stmt = stmt.where(Repost.deleted.is_(False))
        count_stmt = count_stmt.where(Repost.deleted.is_(False))
    selected_range = date_range(year, month, day)
    if selected_range:
        start, end = selected_range
        stmt = stmt.where(Repost.record_created_at >= start, Repost.record_created_at < end)
        count_stmt = count_stmt.where(Repost.record_created_at >= start, Repost.record_created_at < end)
    ordering = timeline_ordering(Repost.record_created_at, Repost.indexed_at, order, Repost.id)
    reposts = list(db.scalars(stmt.order_by(*ordering).limit(limit).offset(offset)).all())
    prime_repost_context(db, reposts)
    return {"items": [repost_out(repost, db) for repost in reposts], "total": db.scalar(count_stmt) or 0}


@router.get("/timeline")
def timeline(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    day: int | None = Query(default=None, ge=1, le=31),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    post_rows = select(
        literal("post").label("kind"),
        Post.id.label("item_id"),
        Post.record_created_at.label("created_at"),
        Post.indexed_at.label("indexed_at"),
    )
    repost_rows = select(
        literal("repost").label("kind"),
        Repost.id.label("item_id"),
        Repost.record_created_at.label("created_at"),
        Repost.indexed_at.label("indexed_at"),
    )
    if not include_deleted:
        post_rows = post_rows.where(Post.deleted.is_(False))
        repost_rows = repost_rows.where(Repost.deleted.is_(False))
    selected_range = date_range(year, month, day)
    if selected_range:
        start, end = selected_range
        post_rows = post_rows.where(Post.record_created_at >= start, Post.record_created_at < end)
        repost_rows = repost_rows.where(Repost.record_created_at >= start, Repost.record_created_at < end)
    combined = union_all(post_rows, repost_rows).subquery()
    total = db.scalar(select(func.count()).select_from(combined)) or 0
    ordering = timeline_ordering(
        combined.c.created_at,
        combined.c.indexed_at,
        order,
        combined.c.kind,
        combined.c.item_id,
    )
    rows = db.execute(select(combined).order_by(*ordering).limit(limit).offset(offset)).all()
    return timeline_response(db, rows, total, limit, offset)


@router.get("/timeline/search")
def search_timeline_by_tag(
    tag: str = Query(min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    normalized = tag.strip().removeprefix("#").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="tag must not be empty")
    lowered = normalized.lower()
    post_rows = (
        select(
            literal("post").label("kind"),
            Post.id.label("item_id"),
            Post.record_created_at.label("created_at"),
            Post.indexed_at.label("indexed_at"),
        )
        .join(Hashtag, Hashtag.post_id == Post.id)
        .where(func.lower(Hashtag.tag) == lowered)
        .distinct()
    )
    repost_rows = (
        select(
            literal("repost").label("kind"),
            Repost.id.label("item_id"),
            Repost.record_created_at.label("created_at"),
            Repost.indexed_at.label("indexed_at"),
        )
        .join(RepostHashtag, RepostHashtag.repost_id == Repost.id)
        .where(func.lower(RepostHashtag.tag) == lowered)
        .distinct()
    )
    if not include_deleted:
        post_rows = post_rows.where(Post.deleted.is_(False))
        repost_rows = repost_rows.where(Repost.deleted.is_(False))
    combined = union_all(post_rows, repost_rows).subquery()
    total = db.scalar(select(func.count()).select_from(combined)) or 0
    ordering = timeline_ordering(
        combined.c.created_at,
        combined.c.indexed_at,
        order,
        combined.c.kind,
        combined.c.item_id,
    )
    rows = db.execute(select(combined).order_by(*ordering).limit(limit).offset(offset)).all()
    return timeline_response(db, rows, total, limit, offset)


@router.get("/posts/{post_id}", response_model=PostDetailOut)
def get_post(post_id: int, include_raw: bool = False, db: Session = Depends(get_db)):
    post = db.scalar(
        select(Post)
        .where(Post.id == post_id, Post.deleted.is_(False))
        .options(
            selectinload(Post.author),
            selectinload(Post.media_links).selectinload(PostMedia.media_asset),
            selectinload(Post.external_links),
        )
    )
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    prime_post_context(db, [post])
    response = post_out(post, db).model_dump()
    if include_raw:
        response["raw_record_json"] = post.raw_record_json
        response["raw_view_json"] = post.raw_view_json
    return response


@router.get("/calendar", response_model=CalendarOut)
def calendar(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    events = union_all(
        select(Post.record_created_at.label("created_at")).where(Post.deleted.is_(False)),
        select(Repost.record_created_at.label("created_at")).where(Repost.deleted.is_(False)),
    ).subquery()
    local_created = local_created_at(events.c.created_at)
    if year is None:
        local_year = func.extract("year", local_created)
        rows = db.execute(
            select(local_year.label("year"), func.count()).group_by(local_year).order_by(local_year)
        ).all()
        return {"years": [{"year": int(row[0]), "count": row[1]} for row in rows if row[0] is not None]}
    if month is None:
        local_year = func.extract("year", local_created)
        local_month = func.extract("month", local_created)
        rows = db.execute(
            select(local_month.label("month"), func.count())
            .where(local_year == year)
            .group_by(local_month)
            .order_by(local_month)
        ).all()
        return {
            "months": [
                {"year": year, "month": int(row[0]), "count": row[1]}
                for row in rows
                if row[0] is not None
            ]
        }
    local_year = func.extract("year", local_created)
    local_month = func.extract("month", local_created)
    local_day = cast(local_created, Date)
    rows = db.execute(
        select(local_day.label("day"), func.count())
        .where(local_year == year, local_month == month)
        .group_by(local_day)
        .order_by(local_day)
    ).all()
    return {"days": [{"date": row[0].isoformat(), "count": row[1]} for row in rows]}


@router.get("/search", response_model=PostListOut)
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
    order: TimelineOrder = "desc",
    db: Session = Depends(get_db),
):
    ts_query = func.plainto_tsquery("simple", q)
    fts_match = Post.search_vector.op("@@")(ts_query)
    like = f"%{q}%"
    fallback_match = or_(
        Post.text.ilike(like),
        Hashtag.tag.ilike(like),
        Mention.handle.ilike(like),
        Mention.text.ilike(like),
        Mention.did.ilike(like),
    )
    matching_query = (
        select(Post.id)
        .outerjoin(Hashtag, Hashtag.post_id == Post.id)
        .outerjoin(Mention, Mention.post_id == Post.id)
        .where(or_(fts_match, fallback_match))
    )
    if not include_deleted:
        matching_query = matching_query.where(Post.deleted.is_(False))
    matching_ids = matching_query.distinct().subquery()
    total = db.scalar(select(func.count()).select_from(matching_ids)) or 0
    ordering = timeline_ordering(Post.record_created_at, Post.indexed_at, order, Post.id)
    posts = list(
        db.scalars(
            select(Post)
            .where(Post.id.in_(select(matching_ids.c.id)))
            .options(
                selectinload(Post.author),
                selectinload(Post.media_links).selectinload(PostMedia.media_asset),
                selectinload(Post.external_links),
            )
            .order_by(*ordering)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    prime_post_context(db, posts)
    return {"items": [post_out(post, db) for post in posts], "total": total}


@router.post("/sync")
def request_sync(x_requested_with: str | None = Header(default=None), db: Session = Depends(get_db)):
    if x_requested_with != "BlueskyArchive":
        raise HTTPException(status_code=403, detail="missing application request header")
    now = datetime.now(timezone.utc)
    state = db.scalar(select(SyncState).where(SyncState.source == "manual_sync"))
    if state is None:
        state = SyncState(source="manual_sync", metadata_json={})
        db.add(state)
    metadata = state.metadata_json or {}
    pending = metadata.get("requested_at")
    if pending and pending != metadata.get("consumed_at"):
        return {"requested": False, "requested_at": pending}
    requested_at = now.isoformat()
    state.metadata_json = {**metadata, "requested_at": requested_at}
    db.commit()
    return {"requested": True, "requested_at": requested_at}


@router.get("/sync")
def sync_status(db: Session = Depends(get_db)):
    state = db.scalar(select(SyncState).where(SyncState.source == "manual_sync"))
    latest_run = db.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
    metadata = state.metadata_json if state else {}
    return {
        "requested_at": metadata.get("requested_at") if metadata else None,
        "consumed_at": metadata.get("consumed_at") if metadata else None,
        "latest_run": (
            {
                "status": latest_run.status,
                "started_at": latest_run.started_at,
                "finished_at": latest_run.finished_at,
                "fetched_count": latest_run.fetched_count,
                "inserted_count": latest_run.inserted_count,
                "updated_count": latest_run.updated_count,
                "error_message": latest_run.error_message,
            }
            if latest_run
            else None
        ),
    }
