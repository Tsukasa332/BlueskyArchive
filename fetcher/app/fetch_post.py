import argparse
import json
import logging
from urllib.parse import urlparse

from sqlalchemy import func, select

from archive.db.models import PostMedia
from archive.db.session import make_session_factory
from app.bluesky_client import BlueskyClient
from app.config import settings
from app.media_downloader import MediaDownloader
from app.sync import POST_COLLECTION, SyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_post_ref(ref: str, client: BlueskyClient) -> tuple[str, str, str]:
    if ref.startswith("at://"):
        parts = ref.split("/")
        if len(parts) < 5:
            raise ValueError("invalid at:// post URI")
        return parts[2], parts[3], parts[4]

    parsed = urlparse(ref)
    path = parsed.path.strip("/").split("/")
    if parsed.netloc == "bsky.app" and len(path) >= 4 and path[0] == "profile" and path[2] == "post":
        actor = path[1]
        did = actor if actor.startswith("did:") else client.resolve_handle(actor)
        return did, POST_COLLECTION, path[3]

    raise ValueError("post ref must be an at:// URI or bsky.app post URL")


def fetch_one(ref: str, dump_embed: bool = False) -> None:
    factory = make_session_factory(settings.database_url)
    client = BlueskyClient(settings.blsky_identifier, settings.blsky_app_password, timeout=settings.request_timeout_seconds)
    downloader = MediaDownloader(settings.media_root, client)
    try:
        client.login()
        repo, collection, rkey = parse_post_ref(ref, client)
        record = client.get_record(repo, collection, rkey)
        uri = record["uri"]

        service = None
        with factory() as session:
            service = SyncService(
                session,
                client,
                downloader,
                page_limit=settings.fetch_page_limit,
                save_own_media=settings.save_own_media,
            )
            views = service._load_post_views([uri])
            view = views.get(uri, {})
            if dump_embed:
                logger.info("record embed=%s", json.dumps((record.get("value") or {}).get("embed"), ensure_ascii=False, sort_keys=True))
                logger.info("view embed=%s", json.dumps(view.get("embed"), ensure_ascii=False, sort_keys=True))
            post, inserted = service.repo.upsert_post(record, view)
            service._save_related_actors(record.get("value") or {}, view)
            service._save_media_for_post(post, record.get("value") or {}, view)
            session.flush()
            media_count = session.scalar(select(func.count()).select_from(PostMedia).where(PostMedia.post_id == post.id)) or 0
            session.commit()

        logger.info("post fetched uri=%s inserted=%s media=%s", uri, inserted, media_count)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and refresh a single Bluesky post archive entry.")
    parser.add_argument("post", help="at:// post URI or https://bsky.app/profile/.../post/... URL")
    parser.add_argument("--dump-embed", action="store_true", help="Log raw record/view embed JSON for diagnostics.")
    args = parser.parse_args()
    fetch_one(args.post, args.dump_embed)


if __name__ == "__main__":
    main()
