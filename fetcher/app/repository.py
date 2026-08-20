from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select, text
from sqlalchemy.orm import Session

from archive.bluesky_embed import embedded_record_ref, hashtag_rows, quote_uri
from archive.db.models import Actor, Embed, ExternalLink, Hashtag, MediaAsset, MediaCaption, Mention, Post, PostMedia, PostVersion, Repost, RepostHashtag, SyncRun, SyncState

ARCHIVE_SCHEMA_VERSION = 2


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def rkey_from_uri(uri: str) -> str | None:
    parts = uri.rsplit("/", 1)
    return parts[-1] if len(parts) == 2 else None


def subject_view_complete(subject_view: dict[str, Any] | None) -> bool:
    if not isinstance(subject_view, dict):
        return False
    record = subject_view.get("record")
    author = subject_view.get("author")
    return (
        isinstance(record, dict)
        and isinstance(record.get("text"), str)
        and isinstance(author, dict)
        and bool(author.get("did"))
    )


class ArchiveRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._actor_cache: dict[str, Actor] = {}

    def start_run(self) -> SyncRun:
        now = datetime.now(timezone.utc)
        stale_runs = self.session.scalars(select(SyncRun).where(SyncRun.status == "running")).all()
        for stale in stale_runs:
            stale.status = "interrupted"
            stale.finished_at = now
            stale.error_message = "fetcher stopped before the sync run completed"
        run = SyncRun(status="running")
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(self, run: SyncRun, status: str, error: str | None = None) -> None:
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.error_message = error

    def upsert_actor(self, data: dict[str, Any]) -> Actor:
        did = data.get("did")
        if not did:
            raise ValueError("actor did is required")
        actor = self._actor_cache.get(did)
        if actor is None:
            actor = next((item for item in self.session.new if isinstance(item, Actor) and item.did == did), None)
        if actor is None:
            with self.session.no_autoflush:
                actor = self.session.scalar(select(Actor).where(Actor.did == did))
        if actor is None:
            actor = Actor(did=did, raw_json=data)
            self.session.add(actor)
        self._actor_cache[did] = actor
        if "handle" in data:
            actor.handle = data.get("handle")
        if "displayName" in data:
            actor.display_name = data.get("displayName")
        if "description" in data:
            actor.description = data.get("description")
        if "avatar" in data:
            actor.avatar_cid = data.get("avatar")
        if "banner" in data:
            actor.banner_cid = data.get("banner")
        actor.raw_json = {**(actor.raw_json or {}), **data}
        return actor

    def upsert_post(self, record_item: dict[str, Any], view: dict[str, Any] | None = None) -> tuple[Post, bool]:
        view = view or {}
        record = record_item.get("value", {})
        uri = record_item["uri"]
        cid = record_item.get("cid")
        author = view.get("author") or {"did": uri.split("/")[2]}
        actor = self.upsert_actor(author)
        post = self.session.scalar(select(Post).where(Post.uri == uri))
        inserted = post is None
        if post is None:
            post = Post(uri=uri, author_did=actor.did, raw_record_json=record, raw_view_json=view)
            self.session.add(post)
            self.session.flush()
        elif post.cid and cid and post.cid != cid:
            exists = self.session.scalar(select(PostVersion).where(PostVersion.post_id == post.id, PostVersion.cid == post.cid))
            if exists is None:
                self.session.add(PostVersion(post_id=post.id, cid=post.cid, text=post.text, raw_record_json=post.raw_record_json))
        post.cid = cid
        post.author_did = actor.did
        post.rkey = rkey_from_uri(uri)
        post.text = record.get("text") or view.get("record", {}).get("text") or ""
        post.langs = record.get("langs")
        post.reply_root_uri = (record.get("reply") or {}).get("root", {}).get("uri")
        post.reply_parent_uri = (record.get("reply") or {}).get("parent", {}).get("uri")
        post.quote_uri = self._quote_uri(record, view)
        post.indexed_at = parse_dt(view.get("indexedAt"))
        post.record_created_at = parse_dt(record.get("createdAt"))
        post.repo_seen_at = datetime.now(timezone.utc)
        post.deleted = False
        post.archive_schema_version = ARCHIVE_SCHEMA_VERSION
        post.raw_record_json = record
        post.raw_view_json = view
        self._replace_facets(post, record)
        self._replace_embeds(post, record, view)
        self.session.flush()
        self.session.execute(text("UPDATE posts SET text = text WHERE id = :id"), {"id": post.id})
        return post, inserted

    def upsert_repost(self, record_item: dict[str, Any], subject_view: dict[str, Any] | None = None, subject_view_status: str | None = None) -> tuple[Repost, bool]:
        record = record_item.get("value", {})
        uri = record_item["uri"]
        did = uri.split("/")[2]
        self.upsert_actor({"did": did})
        if subject_view and subject_view.get("author"):
            self.upsert_actor(subject_view["author"])
        repost = self.session.scalar(select(Repost).where(Repost.uri == uri))
        inserted = repost is None
        if repost is None:
            repost = Repost(uri=uri, actor_did=did, subject_uri=record.get("subject", {}).get("uri", ""), raw_record_json=record, raw_view_json={})
            self.session.add(repost)
        existing_raw_view = repost.raw_view_json or {}
        existing_subject_view = existing_raw_view.get("subject_view") or {}
        existing_subject_view_status = existing_raw_view.get("subject_view_status")
        repost.cid = record_item.get("cid")
        repost.actor_did = did
        repost.subject_uri = record.get("subject", {}).get("uri", "")
        repost.subject_cid = record.get("subject", {}).get("cid")
        repost.record_created_at = parse_dt(record.get("createdAt"))
        repost.repo_seen_at = datetime.now(timezone.utc)
        repost.deleted = False
        repost.archive_schema_version = ARCHIVE_SCHEMA_VERSION
        repost.raw_record_json = record
        stored_subject_view = subject_view
        preserved_existing_view = subject_view_complete(existing_subject_view) and not subject_view_complete(subject_view)
        if preserved_existing_view:
            stored_subject_view = existing_subject_view
        repost.raw_view_json = {
            "record_item": record_item,
            "subject_view": stored_subject_view or existing_subject_view,
            "subject_view_status": existing_subject_view_status if preserved_existing_view else (subject_view_status or existing_subject_view_status),
            "subject_view_attempted_at": existing_raw_view.get("subject_view_attempted_at") if preserved_existing_view else (datetime.now(timezone.utc).isoformat() if subject_view_status else existing_raw_view.get("subject_view_attempted_at")),
        }
        self.session.flush()
        if subject_view_complete(subject_view):
            self.replace_repost_hashtags(repost, subject_view.get("record") or {})
        return repost, inserted

    def replace_repost_hashtags(self, repost: Repost, subject_record: dict[str, Any]) -> None:
        self.session.execute(delete(RepostHashtag).where(RepostHashtag.repost_id == repost.id))
        for row in hashtag_rows(subject_record):
            self.session.add(RepostHashtag(repost_id=repost.id, **row))

    @staticmethod
    def _repost_needs_subject_view(repost: Repost, retry_after_seconds: int = 86400) -> bool:
        raw_view = repost.raw_view_json or {}
        status = raw_view.get("subject_view_status")
        if status in {"missing", "unavailable", "incomplete", "media_missing"}:
            attempted_at = parse_dt(raw_view.get("subject_view_attempted_at"))
            minimum_retry_seconds = 86400 if status in {"missing", "unavailable"} else retry_after_seconds
            effective_retry_seconds = max(retry_after_seconds, minimum_retry_seconds)
            return attempted_at is None or (datetime.now(timezone.utc) - attempted_at).total_seconds() >= effective_retry_seconds
        subject_view = raw_view.get("subject_view") or {}
        return not subject_view_complete(subject_view)

    def replace_post_media_links(self, post: Post, expected_cids: set[str]) -> None:
        links = self.session.scalars(
            select(PostMedia).join(MediaAsset).where(PostMedia.post_id == post.id)
        ).all()
        for link in links:
            if link.media_asset.cid not in expected_cids:
                self.session.delete(link)

    def posts_needing_refresh(self, records: list[dict[str, Any]], seen_at: datetime) -> list[dict[str, Any]]:
        uris = [record["uri"] for record in records]
        existing = {
            post.uri: post
            for post in self.session.scalars(select(Post).where(Post.uri.in_(uris))).all()
        } if uris else {}
        pending: list[dict[str, Any]] = []
        for record in records:
            post = existing.get(record["uri"])
            if (
                post is None
                or post.cid != record.get("cid")
                or (post.archive_schema_version or 0) < ARCHIVE_SCHEMA_VERSION
            ):
                pending.append(record)
            else:
                post.repo_seen_at = seen_at
                post.deleted = False
        return pending

    def reposts_needing_refresh(self, records: list[dict[str, Any]], seen_at: datetime) -> list[dict[str, Any]]:
        uris = [record["uri"] for record in records]
        existing = {
            repost.uri: repost
            for repost in self.session.scalars(select(Repost).where(Repost.uri.in_(uris))).all()
        } if uris else {}
        pending: list[dict[str, Any]] = []
        for record in records:
            repost = existing.get(record["uri"])
            if (
                repost is None
                or repost.cid != record.get("cid")
                or (repost.archive_schema_version or 0) < ARCHIVE_SCHEMA_VERSION
                or self._repost_needs_subject_view(repost)
            ):
                pending.append(record)
            else:
                repost.repo_seen_at = seen_at
                repost.deleted = False
        return pending

    def reposts_for_subject_repair(
        self,
        refs: list[str] | None = None,
        *,
        limit: int = 100,
        retry_after_seconds: int = 900,
        force: bool = False,
    ) -> list[Repost]:
        query = select(Repost).where(Repost.deleted.is_(False))
        if refs:
            query = query.where(or_(Repost.uri.in_(refs), Repost.subject_uri.in_(refs)))
        query = query.order_by(Repost.record_created_at.desc().nullslast()).limit(limit)
        reposts = list(self.session.scalars(query).all())
        if force:
            return reposts
        return [repost for repost in reposts if self._repost_needs_subject_view(repost, retry_after_seconds)]

    def upsert_media_asset(self, *, post: Post | None, cid: str, path: str, media_type: str, mime_type: str | None, size_bytes: int | None, width: int | None, height: int | None, alt_text: str | None, raw_json: dict[str, Any], position: int) -> MediaAsset:
        asset = self.session.scalar(select(MediaAsset).where(MediaAsset.cid == cid))
        if asset is None:
            asset = MediaAsset(cid=cid, path=path, media_type=media_type, raw_json=raw_json)
            self.session.add(asset)
            self.session.flush()
        asset.mime_type = mime_type or asset.mime_type
        asset.size_bytes = size_bytes or asset.size_bytes
        asset.path = path
        asset.width = width
        asset.height = height
        asset.alt_text = alt_text
        asset.media_type = media_type
        asset.raw_json = raw_json
        if post is None:
            return asset
        link = self.session.scalar(select(PostMedia).where(PostMedia.post_id == post.id, PostMedia.media_asset_id == asset.id))
        if link is None:
            self.session.add(PostMedia(post_id=post.id, media_asset_id=asset.id, position=position))
        else:
            link.position = position
        return asset

    def replace_media_captions(self, asset: MediaAsset, captions: list[dict[str, Any]]) -> None:
        self.session.execute(delete(MediaCaption).where(MediaCaption.media_asset_id == asset.id))
        for caption in captions:
            self.session.add(
                MediaCaption(
                    media_asset_id=asset.id,
                    lang=caption["lang"],
                    cid=caption["cid"],
                    path=caption["path"],
                    mime_type=caption.get("mime_type"),
                    size_bytes=caption.get("size_bytes"),
                )
            )

    def get_state(self, source: str) -> SyncState:
        state = self.session.scalar(select(SyncState).where(SyncState.source == source))
        if state is None:
            state = SyncState(source=source, metadata_json={})
            self.session.add(state)
            self.session.flush()
        return state

    def mark_state_success(self, source: str, cursor: str | None, last_seen: datetime | None) -> None:
        state = self.get_state(source)
        state.cursor = cursor
        state.last_seen_indexed_at = last_seen or state.last_seen_indexed_at
        state.last_success_at = datetime.now(timezone.utc)

    def mark_state_error(self, source: str) -> None:
        self.get_state(source).last_error_at = datetime.now(timezone.utc)

    def checkpoint_state(self, source: str, cursor: str | None, metadata: dict[str, Any]) -> None:
        state = self.get_state(source)
        state.cursor = cursor
        state.metadata_json = metadata

    def mark_missing_posts_deleted(self, *, author_did: str, existing_uris: set[str]) -> int:
        posts = self.session.scalars(select(Post).where(Post.author_did == author_did, Post.deleted.is_(False))).all()
        deleted = 0
        for post in posts:
            if post.uri not in existing_uris:
                post.deleted = True
                deleted += 1
        return deleted

    def mark_post_deleted(self, *, uri: str) -> int:
        post = self.session.scalar(select(Post).where(Post.uri == uri, Post.deleted.is_(False)))
        if post is None:
            return 0
        post.deleted = True
        return 1

    def mark_repost_deleted(self, *, uri: str) -> int:
        repost = self.session.scalar(select(Repost).where(Repost.uri == uri, Repost.deleted.is_(False)))
        if repost is None:
            return 0
        repost.deleted = True
        return 1

    def mark_posts_not_seen_since(self, *, author_did: str, scan_started_at: datetime) -> int:
        posts = self.session.scalars(
            select(Post).where(
                Post.author_did == author_did,
                Post.deleted.is_(False),
                (Post.repo_seen_at.is_(None) | (Post.repo_seen_at < scan_started_at)),
            )
        ).all()
        for post in posts:
            post.deleted = True
        return len(posts)

    def mark_reposts_not_seen_since(self, *, actor_did: str, scan_started_at: datetime) -> int:
        reposts = self.session.scalars(
            select(Repost).where(
                Repost.actor_did == actor_did,
                Repost.deleted.is_(False),
                (Repost.repo_seen_at.is_(None) | (Repost.repo_seen_at < scan_started_at)),
            )
        ).all()
        for repost in reposts:
            repost.deleted = True
        return len(reposts)

    def save_following_dids(self, dids: list[str]) -> None:
        state = self.get_state("following")
        state.metadata_json = {
            "following_dids": sorted(set(dids)),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        state.last_success_at = datetime.now(timezone.utc)

    def _replace_facets(self, post: Post, record: dict[str, Any]) -> None:
        self.session.execute(delete(Mention).where(Mention.post_id == post.id))
        self.session.execute(delete(Hashtag).where(Hashtag.post_id == post.id))
        for facet in record.get("facets") or []:
            index = facet.get("index") or {}
            for feature in facet.get("features") or []:
                ftype = feature.get("$type", "")
                if ftype.endswith("#mention"):
                    self.session.add(Mention(post_id=post.id, did=feature.get("did"), text=feature.get("did"), start_byte=index.get("byteStart"), end_byte=index.get("byteEnd")))
                elif ftype.endswith("#tag"):
                    pass
        for row in hashtag_rows(record):
            self.session.add(Hashtag(post_id=post.id, **row))

    def _replace_embeds(self, post: Post, record: dict[str, Any], view: dict[str, Any]) -> None:
        self.session.execute(delete(Embed).where(Embed.post_id == post.id))
        self.session.execute(delete(ExternalLink).where(ExternalLink.post_id == post.id))
        record_embed = record.get("embed") or {}
        view_embed = view.get("embed") or {}
        embed = record_embed or view_embed
        if not embed:
            return
        etype = embed.get("$type") or embed.get("type") or "unknown"
        ref = embedded_record_ref(record_embed, view_embed)
        self.session.add(
            Embed(
                post_id=post.id,
                embed_type=etype,
                uri=ref.get("uri"),
                cid=ref.get("cid"),
                raw_json={"record": record_embed, "view": view_embed},
            )
        )
        external = self._external_embed(record_embed)
        external_view = self._external_embed(view_embed)
        if external:
            thumb = external.get("thumb")
            thumb_cid = None
            if isinstance(thumb, dict):
                ref = thumb.get("ref") or thumb.get("$link")
                if isinstance(ref, dict):
                    thumb_cid = ref.get("$link")
                elif isinstance(ref, str):
                    thumb_cid = ref
            self.session.add(
                ExternalLink(
                    post_id=post.id,
                    uri=external.get("uri", ""),
                    title=external.get("title"),
                    description=external.get("description"),
                    thumb_cid=thumb_cid,
                    raw_json={"record": external, "view": external_view or {}},
                )
            )
        elif external_view:
            self.session.add(
                ExternalLink(
                    post_id=post.id,
                    uri=external_view.get("uri", ""),
                    title=external_view.get("title"),
                    description=external_view.get("description"),
                    thumb_cid=None,
                    raw_json={"record": {}, "view": external_view},
                )
            )

    def _external_embed(self, embed: dict[str, Any]) -> dict[str, Any] | None:
        if embed.get("external"):
            return embed["external"]
        media = embed.get("media") or {}
        if media.get("external"):
            return media["external"]
        return None

    def _quote_uri(self, record: dict[str, Any], view: dict[str, Any]) -> str | None:
        return quote_uri(record.get("embed"), view.get("embed"))
