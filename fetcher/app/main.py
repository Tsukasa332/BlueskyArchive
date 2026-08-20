import logging
import time

from sqlalchemy import select

from archive.db.models import SyncState
from archive.db.session import make_session_factory
from app.bluesky_client import BlueskyClient
from app.config import settings
from app.media_downloader import MediaDownloader
from app.sync import SyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)
MANUAL_SYNC_SOURCE = "manual_sync"
POLL_SECONDS = 5


def pending_manual_sync_request(session) -> str | None:
    state = session.scalar(select(SyncState).where(SyncState.source == MANUAL_SYNC_SOURCE))
    if state is None:
        return None
    metadata = state.metadata_json or {}
    requested_at = metadata.get("requested_at")
    return requested_at if requested_at and requested_at != metadata.get("consumed_at") else None


def mark_manual_sync_consumed(session, requested_at: str | None) -> None:
    state = session.scalar(select(SyncState).where(SyncState.source == MANUAL_SYNC_SOURCE))
    if state is None:
        return
    metadata = state.metadata_json or {}
    if not requested_at:
        return
    state.metadata_json = {**metadata, "consumed_at": requested_at}
    session.commit()


def main() -> None:
    factory = make_session_factory(settings.database_url)
    client = BlueskyClient(settings.blsky_identifier, settings.blsky_app_password, timeout=settings.request_timeout_seconds)
    downloader = MediaDownloader(
        settings.media_root,
        client,
        settings.media_min_free_bytes,
        settings.media_max_file_bytes,
        settings.media_max_total_bytes,
        settings.media_total_scan_interval_seconds,
    )
    try:
        while True:
            request_token = None
            try:
                with factory() as session:
                    request_token = pending_manual_sync_request(session)
                    SyncService(
                        session,
                        client,
                        downloader,
                        settings.fetch_page_limit,
                        settings.full_reconcile_interval_seconds,
                        settings.save_own_media,
                    ).sync_once()
                    mark_manual_sync_consumed(session, request_token)
            except Exception:
                logger.exception("sync cycle failed; retrying in %s seconds", settings.error_backoff_seconds)
                time.sleep(settings.error_backoff_seconds)
                continue
            logger.info("sleeping for %s seconds", settings.fetch_interval_seconds)
            slept = 0
            while slept < settings.fetch_interval_seconds:
                time.sleep(min(POLL_SECONDS, settings.fetch_interval_seconds - slept))
                slept += POLL_SECONDS
                with factory() as session:
                    if pending_manual_sync_request(session):
                        logger.info("manual sync requested")
                        break
    finally:
        client.close()


if __name__ == "__main__":
    main()
