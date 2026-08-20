import argparse
import logging

from archive.db.session import make_session_factory
from app.bluesky_client import BlueskyClient
from app.config import settings
from app.repository import ArchiveRepository
from app.sync import POST_COLLECTION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def reconcile_posts() -> None:
    factory = make_session_factory(settings.database_url)
    client = BlueskyClient(settings.blsky_identifier, settings.blsky_app_password, timeout=settings.request_timeout_seconds)
    try:
        client.login()
        if not client.did:
            raise RuntimeError("login did not return a DID")

        existing_uris: set[str] = set()
        cursor: str | None = None
        pages = 0
        while True:
            page = client.list_records(POST_COLLECTION, cursor=cursor, limit=settings.fetch_page_limit)
            pages += 1
            for record in page.get("records", []):
                uri = record.get("uri")
                if uri:
                    existing_uris.add(uri)
            cursor = page.get("cursor")
            if not cursor:
                break

        with factory() as session:
            deleted = ArchiveRepository(session).mark_missing_posts_deleted(author_did=client.did, existing_uris=existing_uris)
            session.commit()

        logger.info("post deletion reconciliation completed pages=%s existing=%s deleted=%s", pages, len(existing_uris), deleted)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark locally archived posts as deleted when they no longer exist in Bluesky repo records.")
    parser.parse_args()
    reconcile_posts()


if __name__ == "__main__":
    main()
