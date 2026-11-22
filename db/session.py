from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings


@lru_cache
def get_engine(url: str | None = None):
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any exception."""
    s = _factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
