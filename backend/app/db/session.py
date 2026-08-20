from collections.abc import Generator

from sqlalchemy.orm import Session

from archive.db.session import make_session_factory
from app.core.config import settings

SessionLocal = make_session_factory(settings.database_url)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
