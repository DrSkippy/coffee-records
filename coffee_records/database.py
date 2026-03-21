"""SQLAlchemy engine, session factory, and declarative base."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(database_url: str, pool_size: int = 5) -> None:
    """Initialize the database engine and session factory.

    Args:
        database_url: Full SQLAlchemy connection URL.
        pool_size: Connection pool size.
    """
    global _engine, _SessionLocal
    _engine = create_engine(database_url, pool_size=pool_size, pool_pre_ping=True)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_engine():  # type: ignore[return]
    """Return the initialized engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_session() -> Session:
    """Return a new database session.

    Returns:
        A new SQLAlchemy Session bound to the configured engine.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()
