import logging

from sqlalchemy import select

from archive.db.models import Repost
from archive.db.session import make_session_factory
from app.config import settings
from app.repository import ArchiveRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def backfill(batch_size: int = 500) -> tuple[int, int]:
    factory = make_session_factory(settings.database_url)
    processed = skipped = 0
    last_id = 0
    with factory() as session:
        repo = ArchiveRepository(session)
        while True:
            reposts = list(session.scalars(
                select(Repost).where(Repost.id > last_id).order_by(Repost.id).limit(batch_size)
            ).all())
            if not reposts:
                break
            for repost in reposts:
                last_id = repost.id
                subject_view = (repost.raw_view_json or {}).get("subject_view") or {}
                subject_record = subject_view.get("record")
                if not isinstance(subject_record, dict):
                    skipped += 1
                    continue
                repo.replace_repost_hashtags(repost, subject_record)
                processed += 1
            session.commit()
            logger.info("repost hashtag backfill checkpoint processed=%s skipped=%s last_id=%s", processed, skipped, last_id)
    return processed, skipped


def main() -> None:
    processed, skipped = backfill()
    logger.info("repost hashtag backfill completed processed=%s skipped=%s", processed, skipped)


if __name__ == "__main__":
    main()
