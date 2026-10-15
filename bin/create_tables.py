#!/usr/bin/env python
"""One-shot script to create all database tables against the real PostgreSQL instance."""

import logging
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import ShotDefaultsSeed, load_config  # noqa: E402
from coffee_records.database import (  # noqa: E402
    Base,
    get_engine,
    get_session,
    init_db,
)

# Import all models so they are registered with Base
import coffee_records.models  # noqa: E402,F401
from coffee_records.models.settings import (  # noqa: E402
    SHOT_DEFAULTS_ID,
    ShotDefaults,
)

logger = logging.getLogger(__name__)


def seed_defaults(seed: ShotDefaultsSeed) -> bool:
    """Insert the shot_defaults singleton row if it doesn't exist yet.

    Args:
        seed: Initial values (config.yaml ``shot_defaults_seed``).

    Returns:
        True if a row was inserted.
    """
    with get_session() as session:
        if session.get(ShotDefaults, SHOT_DEFAULTS_ID) is not None:
            logger.info("shot_defaults already present, skipping seed.")
            return False
        session.add(ShotDefaults(id=SHOT_DEFAULTS_ID, **seed.model_dump()))
        session.commit()
        logger.info("Seeded shot_defaults with default values.")
        return True


def main() -> None:
    """Create all tables and seed initial data."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = load_config()
    logger.info(
        "Connecting to: %s:%s/%s",
        config.database.host,
        config.database.port,
        config.database.name,
    )
    init_db(config.database.get_url(), pool_size=1)
    Base.metadata.create_all(get_engine())
    logger.info("Tables created successfully:")
    for table in Base.metadata.sorted_tables:
        logger.info("  - %s", table.name)
    seed_defaults(config.shot_defaults_seed)


if __name__ == "__main__":
    main()
