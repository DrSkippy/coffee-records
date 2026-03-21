"""Pytest configuration and shared fixtures."""

import os
from collections.abc import Generator

import pytest
from flask.testing import FlaskClient

# Use SQLite in-memory for tests (no PostgreSQL needed)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")


@pytest.fixture(scope="session")
def app() -> Generator[object, None, None]:
    """Create test application with SQLite in-memory database."""
    from coffee_records import create_app
    from coffee_records.database import Base, get_engine

    flask_app = create_app(database_url="sqlite:///:memory:")
    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        engine = get_engine()
        # Import all models to register with Base
        import coffee_records.models  # noqa: F401

        Base.metadata.create_all(engine)
        yield flask_app
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(app: object) -> FlaskClient:
    """Return a test client for the app."""
    from flask import Flask

    flask_app: Flask = app  # type: ignore[assignment]
    return flask_app.test_client()


@pytest.fixture(autouse=True)
def clean_tables(app: object) -> Generator[None, None, None]:
    """Truncate all tables between tests."""
    from flask import Flask

    from coffee_records.database import Base, get_session

    flask_app: Flask = app  # type: ignore[assignment]
    with flask_app.app_context():
        yield
        with get_session() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
