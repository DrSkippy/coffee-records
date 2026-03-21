#!/usr/bin/env python
"""One-shot script to create all database tables against the real PostgreSQL instance."""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import load_config
from coffee_records.database import Base, get_engine, init_db

# Import all models so they are registered with Base
import coffee_records.models  # noqa: F401


def main() -> None:
    """Create all tables."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables created successfully:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")


if __name__ == "__main__":
    main()
