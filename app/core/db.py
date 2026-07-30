"""SQLAlchemy engine / session / Base and the FastAPI `get_db` dependency.

Postgres in production (via DATABASE_URL); SQLite fallback for local tests so the
suite runs with zero infrastructure. The `Base` here is the declarative base every
model in `models.py` inherits from.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine():
    url = settings.resolved_database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # Needed so a SQLite connection can be shared across FastAPI threads.
        connect_args["check_same_thread"] = False
    return create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)


engine = _make_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables from the metadata.

    Convenience for tests and first-run SQLite use. Production schema is managed by
    Alembic migrations (`alembic upgrade head`), but calling this is idempotent.
    """
    # Import models so their tables are registered on Base.metadata before create_all.
    from app.core import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
