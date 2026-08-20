import argparse
import logging

from archive.db.session import make_session_factory
from app.bluesky_client import BlueskyClient
from app.config import settings
from app.media_downloader import MediaDownloader
from app.sync import SyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def repair(refs: list[str]) -> int:
    factory = make_session_factory(settings.database_url)
    client = BlueskyClient(
        settings.blsky_identifier,
        settings.blsky_app_password,
        timeout=settings.request_timeout_seconds,
    )
    downloader = MediaDownloader(
        settings.media_root,
        client,
        settings.media_min_free_bytes,
        settings.media_max_file_bytes,
        settings.media_max_total_bytes,
        settings.media_total_scan_interval_seconds,
    )
    try:
        client.login()
        with factory() as session:
            service = SyncService(session, client, downloader, settings.fetch_page_limit)
            matches = service.repo.reposts_for_subject_repair(refs, limit=max(100, len(refs)), force=True)
            missing = [
                ref for ref in refs
                if not any(ref in {repost.uri, repost.subject_uri} for repost in matches)
            ]
            if missing:
                raise RuntimeError(f"no archived repost matches: {', '.join(missing)}")
            repaired = service.repair_repost_subjects(refs, limit=max(100, len(refs)), force=True)
            return repaired
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair archived repost subject views and media without inserting subjects into posts."
    )
    parser.add_argument(
        "refs",
        nargs="+",
        help="Archived repost URI or its subject app.bsky.feed.post URI (at:// form).",
    )
    args = parser.parse_args()
    repaired = repair(args.refs)
    logger.info("repost repair finished repaired=%s", repaired)


if __name__ == "__main__":
    main()
