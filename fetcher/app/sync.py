import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from archive.bluesky_embed import direct_image_items, direct_media_embed, direct_video_items, embedded_record, quote_uri, video_embed
from app.bluesky_client import BlueskyClient
from app.media_downloader import MediaCapacityError, MediaDownloader, blob_cid, blob_cid_from_url
from app.repository import ArchiveRepository, parse_dt, subject_view_complete

logger = logging.getLogger(__name__)
POST_COLLECTION = "app.bsky.feed.post"
REPOST_COLLECTION = "app.bsky.feed.repost"


class SyncService:
    def __init__(
        self,
        session: Session,
        client: BlueskyClient,
        media_downloader: MediaDownloader,
        page_limit: int = 100,
        full_reconcile_interval_seconds: int = 86400,
        save_own_media: bool = False,
    ) -> None:
        self.session = session
        self.client = client
        self.media_downloader = media_downloader
        self.page_limit = page_limit
        self.full_reconcile_interval = timedelta(seconds=full_reconcile_interval_seconds)
        self.save_own_media = save_own_media
        self.repo = ArchiveRepository(session)
        self.current_source = "startup"

    def sync_once(self) -> None:
        run = self.repo.start_run()
        run_id = run.id
        self.session.commit()
        try:
            self.client.login()
            self.current_source = "following"
            self._sync_following()
            self.current_source = "posts"
            fetched, inserted, updated, deleted = self._sync_posts()
            self.current_source = "reposts"
            repost_fetched, repost_inserted, repost_updated, repost_deleted = self._sync_reposts()
            run = self.session.get(type(run), run_id)
            if run is None:
                raise RuntimeError("sync run disappeared")
            run.fetched_count = fetched + repost_fetched
            run.inserted_count = inserted + repost_inserted
            run.updated_count = updated + repost_updated
            run.deleted_count = deleted + repost_deleted
            self.repo.finish_run(run, "success")
            self.session.commit()
            logger.info("sync completed fetched=%s inserted=%s updated=%s deleted=%s", run.fetched_count, run.inserted_count, run.updated_count, run.deleted_count)
        except Exception as exc:
            logger.exception("sync failed")
            self.session.rollback()
            run = self.session.get(type(run), run_id)
            if run is not None:
                self.repo.finish_run(run, "error", str(exc))
            self.repo.mark_state_error(self.current_source)
            self.session.commit()
            raise

    def _sync_following(self) -> None:
        if not self.client.did:
            return
        state = self.repo.get_state("following")
        now = datetime.now(timezone.utc)
        if state.last_success_at and now - state.last_success_at < timedelta(hours=1):
            return
        dids: list[str] = []
        cursor: str | None = None
        try:
            while True:
                data = self.client.get_follows(self.client.did, cursor=cursor, limit=100)
                for actor in data.get("follows", []):
                    did = actor.get("did")
                    if did:
                        dids.append(did)
                        self.repo.upsert_actor(actor)
                cursor = data.get("cursor")
                if not cursor:
                    break
            self.repo.save_following_dids(dids)
            self.session.commit()
            logger.info("following synced count=%s", len(set(dids)))
        except Exception:
            logger.warning("failed to sync following list", exc_info=True)
            self.session.rollback()

    def _sync_posts(self) -> tuple[int, int, int, int]:
        state = self.repo.get_state("posts")
        metadata = dict(state.metadata_json or {})
        now = datetime.now(timezone.utc)
        full_scan = self._full_scan_required(metadata, now)
        if state.cursor and metadata.get("sync_mode") in {"full", "incremental"}:
            full_scan = metadata["sync_mode"] == "full"
        else:
            metadata = self._start_scan_metadata(metadata, now, full_scan)
            state.cursor = None
            self.session.commit()
        cursor = state.cursor
        boundary_rkey = metadata.get("boundary_rkey")
        newest_rkey = metadata.get("run_newest_rkey") or boundary_rkey
        scan_started_at = parse_dt(metadata.get("scan_started_at")) or now
        fetched = inserted = updated = 0
        deleted = 0
        newest_created_at: datetime | None = state.last_seen_indexed_at
        while True:
            page = self.client.list_records(POST_COLLECTION, cursor=cursor, limit=self.page_limit)
            records = page.get("records", [])
            stop_after_page = False
            candidates: list[dict[str, Any]] = []
            for item in records:
                rkey = item.get("uri", "").rsplit("/", 1)[-1]
                if newest_rkey is None or rkey > newest_rkey:
                    newest_rkey = rkey
                if not full_scan and boundary_rkey and rkey <= boundary_rkey:
                    stop_after_page = True
                    continue
                created_at = parse_dt((item.get("value") or {}).get("createdAt"))
                if created_at and (newest_created_at is None or created_at > newest_created_at):
                    newest_created_at = created_at
                candidates.append(item)
            pending_records = self.repo.posts_needing_refresh(candidates, datetime.now(timezone.utc)) if full_scan else candidates
            views = self._load_post_views([item["uri"] for item in pending_records])
            for item in pending_records:
                post, was_inserted = self.repo.upsert_post(item, views.get(item["uri"]))
                self._save_related_actors(item.get("value") or {}, views.get(item["uri"]) or {})
                self._save_media_for_post(post, item.get("value") or {}, views.get(item["uri"]) or {})
                fetched += 1
                inserted += int(was_inserted)
                updated += int(not was_inserted)
            cursor = page.get("cursor")
            metadata["run_newest_rkey"] = newest_rkey
            self.repo.checkpoint_state("posts", cursor, metadata)
            self.session.commit()
            if stop_after_page or not cursor or not records:
                if stop_after_page:
                    self._log_boundary_stop("posts", records, boundary_rkey, newest_rkey, full_scan)
                    if not full_scan and self.client.did and self._boundary_record_missing(records, boundary_rkey):
                        boundary_uri = f"at://{self.client.did}/{POST_COLLECTION}/{boundary_rkey}"
                        boundary_deleted = self.repo.mark_post_deleted(uri=boundary_uri)
                        deleted += boundary_deleted
                        if boundary_deleted:
                            logger.info("missing post boundary marked deleted uri=%s", boundary_uri)
                if full_scan and self.client.did and not cursor:
                    deleted = self.repo.mark_posts_not_seen_since(author_did=self.client.did, scan_started_at=scan_started_at)
                    logger.info("post reconciliation completed deleted=%s", deleted)
                self._finish_scan("posts", metadata, newest_rkey, newest_created_at, full_scan, now)
                self.session.commit()
                break
        return fetched, inserted, updated, deleted

    def _sync_reposts(self) -> tuple[int, int, int, int]:
        repaired = self.repair_repost_subjects(limit=100, retry_after_seconds=900)
        state = self.repo.get_state("reposts")
        metadata = dict(state.metadata_json or {})
        now = datetime.now(timezone.utc)
        full_scan = self._full_scan_required(metadata, now)
        if state.cursor and metadata.get("sync_mode") in {"full", "incremental"}:
            full_scan = metadata["sync_mode"] == "full"
        else:
            metadata = self._start_scan_metadata(metadata, now, full_scan)
            state.cursor = None
            self.session.commit()
        cursor = state.cursor
        boundary_rkey = metadata.get("boundary_rkey")
        newest_rkey = metadata.get("run_newest_rkey") or boundary_rkey
        scan_started_at = parse_dt(metadata.get("scan_started_at")) or now
        fetched = inserted = 0
        updated = repaired
        deleted = 0
        newest_created_at: datetime | None = state.last_seen_indexed_at
        while True:
            page = self.client.list_records(REPOST_COLLECTION, cursor=cursor, limit=self.page_limit)
            records = page.get("records", [])
            stop_after_page = False
            candidates: list[dict[str, Any]] = []
            for item in records:
                rkey = item.get("uri", "").rsplit("/", 1)[-1]
                if newest_rkey is None or rkey > newest_rkey:
                    newest_rkey = rkey
                created_at = parse_dt((item.get("value") or {}).get("createdAt"))
                if created_at and (newest_created_at is None or created_at > newest_created_at):
                    newest_created_at = created_at
                if not full_scan and boundary_rkey and rkey <= boundary_rkey:
                    stop_after_page = True
                    continue
                candidates.append(item)
            pending_records = self.repo.reposts_needing_refresh(candidates, datetime.now(timezone.utc)) if full_scan else candidates
            subject_views = self._load_post_views([
                (item.get("value") or {}).get("subject", {}).get("uri")
                for item in pending_records
                if (item.get("value") or {}).get("subject", {}).get("uri")
            ])
            for item in pending_records:
                subject_uri = (item.get("value") or {}).get("subject", {}).get("uri")
                subject_view = subject_views.get(subject_uri or "")
                if subject_view_complete(subject_view):
                    subject_view_status = "ok"
                elif subject_view:
                    subject_view_status = "incomplete"
                else:
                    subject_view_status = "missing"
                _, was_inserted = self.repo.upsert_repost(item, subject_view, subject_view_status)
                fetched += 1
                inserted += int(was_inserted)
                updated += int(not was_inserted)
            cursor = page.get("cursor")
            metadata["run_newest_rkey"] = newest_rkey
            self.repo.checkpoint_state("reposts", cursor, metadata)
            self.session.commit()
            if stop_after_page or not cursor or not records:
                if stop_after_page:
                    self._log_boundary_stop("reposts", records, boundary_rkey, newest_rkey, full_scan)
                    if not full_scan and self.client.did and self._boundary_record_missing(records, boundary_rkey):
                        boundary_uri = f"at://{self.client.did}/{REPOST_COLLECTION}/{boundary_rkey}"
                        boundary_deleted = self.repo.mark_repost_deleted(uri=boundary_uri)
                        deleted += boundary_deleted
                        if boundary_deleted:
                            logger.info("missing repost boundary marked deleted uri=%s", boundary_uri)
                if full_scan and self.client.did and not cursor:
                    deleted = self.repo.mark_reposts_not_seen_since(actor_did=self.client.did, scan_started_at=scan_started_at)
                    logger.info("repost reconciliation completed deleted=%s", deleted)
                self._finish_scan("reposts", metadata, newest_rkey, newest_created_at, full_scan, now)
                self.session.commit()
                break
        return fetched, inserted, updated, deleted

    def repair_repost_subjects(
        self,
        refs: list[str] | None = None,
        *,
        limit: int = 100,
        retry_after_seconds: int = 900,
        force: bool = False,
    ) -> int:
        reposts = self.repo.reposts_for_subject_repair(
            refs,
            limit=limit,
            retry_after_seconds=retry_after_seconds,
            force=force,
        )
        if not reposts:
            return 0
        subject_views = self._load_post_views([repost.subject_uri for repost in reposts])
        repaired = 0
        for repost in reposts:
            record_item = (repost.raw_view_json or {}).get("record_item") or {
                "uri": repost.uri,
                "cid": repost.cid,
                "value": repost.raw_record_json or {},
            }
            subject_view = subject_views.get(repost.subject_uri)
            if subject_view_complete(subject_view):
                status = "ok"
            elif subject_view:
                status = "incomplete"
            else:
                status = "missing"
            self.repo.upsert_repost(record_item, subject_view, status)
            repaired += 1
        self.session.commit()
        logger.info("repost subject repair completed requested=%s processed=%s", len(refs or []), repaired)
        return repaired

    @staticmethod
    def _boundary_record_missing(records: list[dict[str, Any]], boundary_rkey: str | None) -> bool:
        if not boundary_rkey:
            return False
        rkeys = [item.get("uri", "").rsplit("/", 1)[-1] for item in records]
        return boundary_rkey not in rkeys and any(rkey < boundary_rkey for rkey in rkeys)

    @staticmethod
    def _log_boundary_stop(source: str, records: list[dict[str, Any]], boundary_rkey: str | None, newest_rkey: str | None, full_scan: bool) -> None:
        first_rkey = records[0].get("uri", "").rsplit("/", 1)[-1] if records else None
        last_rkey = records[-1].get("uri", "").rsplit("/", 1)[-1] if records else None
        logger.info(
            "%s scan stopped at boundary full_scan=%s records=%s first_rkey=%s last_rkey=%s boundary_rkey=%s newest_rkey=%s",
            source,
            full_scan,
            len(records),
            first_rkey,
            last_rkey,
            boundary_rkey,
            newest_rkey,
        )

    def _full_scan_required(self, metadata: dict[str, Any], now: datetime) -> bool:
        if not metadata.get("newest_rkey"):
            return True
        last_full = parse_dt(metadata.get("last_full_reconcile_at"))
        return last_full is None or now - last_full >= self.full_reconcile_interval

    @staticmethod
    def _start_scan_metadata(metadata: dict[str, Any], now: datetime, full_scan: bool) -> dict[str, Any]:
        return {
            **metadata,
            "sync_mode": "full" if full_scan else "incremental",
            "boundary_rkey": metadata.get("newest_rkey"),
            "run_newest_rkey": metadata.get("newest_rkey"),
            "scan_started_at": now.isoformat(),
        }

    def _finish_scan(self, source: str, metadata: dict[str, Any], newest_rkey: str | None, newest_created_at: datetime | None, full_scan: bool, now: datetime) -> None:
        finished = {
            **metadata,
            "initial_full_sync_done": True,
            "newest_rkey": newest_rkey,
        }
        for key in ("sync_mode", "boundary_rkey", "run_newest_rkey", "scan_started_at"):
            finished.pop(key, None)
        if full_scan:
            finished["last_full_reconcile_at"] = now.isoformat()
        state = self.repo.get_state(source)
        state.metadata_json = finished
        self.repo.mark_state_success(source, None, newest_created_at)

    def _load_post_views(self, uris: list[str]) -> dict[str, dict[str, Any]]:
        views: dict[str, dict[str, Any]] = {}
        unique_uris = [uri for uri in dict.fromkeys(uris) if uri]
        for start in range(0, len(unique_uris), 25):
            chunk = unique_uris[start : start + 25]
            try:
                data = self.client.get_posts(chunk)
            except Exception:
                logger.warning("failed to load post views for chunk", exc_info=True)
                continue
            for post in data.get("posts", []):
                views[post["uri"]] = post
        return views

    def _save_related_actors(self, record: dict[str, Any], view: dict[str, Any]) -> None:
        dids = set()
        reply = record.get("reply") or {}
        for key in ("root", "parent"):
            did = self._did_from_at_uri((reply.get(key) or {}).get("uri"))
            if did:
                dids.add(did)

        quote_uri = self._quote_uri(record, view)
        quote_did = self._did_from_at_uri(quote_uri)
        if quote_did:
            dids.add(quote_did)

        quote_author = embedded_record(view.get("embed")).get("author") or {}
        if quote_author.get("did"):
            self.repo.upsert_actor(quote_author)
            dids.discard(quote_author["did"])

        for did in dids:
            try:
                self.repo.upsert_actor(self.client.get_profile(did))
            except Exception:
                logger.warning("failed to fetch related actor profile did=%s", did, exc_info=True)

    def _quote_uri(self, record: dict[str, Any], view: dict[str, Any]) -> str | None:
        return quote_uri(record.get("embed"), view.get("embed"))

    def _did_from_at_uri(self, uri: str | None) -> str | None:
        if not uri or not uri.startswith("at://"):
            return None
        parts = uri.split("/")
        return parts[2] if len(parts) > 2 else None

    def _save_media_for_post(self, post, record: dict[str, Any], view: dict[str, Any]) -> None:
        if not self.save_own_media or not self.client.did or post.author_did != self.client.did:
            return
        did = post.author_did
        position = 0
        seen_cids: set[str] = set()
        for image in self._iter_images(record, view):
            cid = self._image_cid(image)
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            try:
                path, mime_type, size = self.media_downloader.save_blob(did, cid, "image")
            except MediaCapacityError:
                raise
            except Exception:
                try:
                    path, mime_type, size = self.media_downloader.save_url(image.get("fullsize") or image.get("thumb") or image.get("thumbnail"), cid, "image")
                except MediaCapacityError:
                    raise
                except Exception:
                    logger.warning("failed to save image cid=%s post=%s", cid, post.uri, exc_info=True)
                    continue
            aspect = image.get("aspectRatio") or {}
            self.repo.upsert_media_asset(post=post, cid=cid, path=path, media_type="image", mime_type=mime_type or image.get("mimeType"), size_bytes=size, width=aspect.get("width") or image.get("width"), height=aspect.get("height") or image.get("height"), alt_text=image.get("alt"), raw_json=image, position=position)
            position += 1
        for video in self._iter_videos(record, view):
            cid = blob_cid(video.get("video")) or video.get("cid")
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            try:
                path, mime_type, size = self.media_downloader.save_blob(did, cid, "video")
            except MediaCapacityError:
                raise
            except Exception:
                logger.warning("failed to save video blob cid=%s post=%s", cid, post.uri, exc_info=True)
                continue
            aspect = video.get("aspectRatio") or {}
            asset = self.repo.upsert_media_asset(post=post, cid=cid, path=path, media_type="video", mime_type=mime_type or video.get("mimeType"), size_bytes=size, width=aspect.get("width"), height=aspect.get("height"), alt_text=video.get("alt"), raw_json=video, position=position)
            self._save_captions(did, asset, video, post.uri)
            position += 1
        self.repo.replace_post_media_links(post, seen_cids)

    def _save_captions(self, did: str, asset, video: dict[str, Any], post_uri: str) -> None:
        saved: list[dict[str, Any]] = []
        for caption in video.get("captions") or []:
            if not isinstance(caption, dict):
                continue
            cid = blob_cid(caption.get("file"))
            lang = caption.get("lang")
            if not cid or not isinstance(lang, str) or not lang:
                continue
            try:
                path, mime_type, size = self.media_downloader.save_blob(did, cid, "caption")
            except MediaCapacityError:
                raise
            except Exception:
                logger.warning(
                    "failed to save video caption cid=%s post=%s",
                    cid,
                    post_uri,
                    exc_info=True,
                )
                continue
            saved.append(
                {
                    "lang": lang,
                    "cid": cid,
                    "path": path,
                    "mime_type": mime_type or "text/vtt",
                    "size_bytes": size,
                }
            )
        self.repo.replace_media_captions(asset, saved)

    def _image_cid(self, image: dict[str, Any]) -> str | None:
        return (
            blob_cid(image.get("image"))
            or blob_cid_from_url(image.get("fullsize"))
            or blob_cid_from_url(image.get("thumb"))
            or image.get("cid")
        )

    def _iter_images(self, record: dict[str, Any], view: dict[str, Any]):
        for embed in (record.get("embed"), view.get("embed")):
            yield from direct_image_items(embed)

    def _iter_videos(self, record: dict[str, Any], view: dict[str, Any]):
        for embed in (record.get("embed"), view.get("embed")):
            yield from direct_video_items(embed)

    @staticmethod
    def _direct_media_embed(embed: Any) -> dict[str, Any]:
        return direct_media_embed(embed)

    def _video_embed(self, record: dict[str, Any], view: dict[str, Any]) -> dict[str, Any] | None:
        video = video_embed(record.get("embed"), view.get("embed"))
        return video or None
