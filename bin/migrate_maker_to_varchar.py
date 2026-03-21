#!/usr/bin/env python
"""Migration: convert shots.maker from PostgreSQL enum to VARCHAR(255)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from coffee_records.config import load_config
from coffee_records.database import get_engine, init_db


def main() -> None:
    """Convert maker column from enum to varchar and drop the enum type."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE shots ALTER COLUMN maker TYPE VARCHAR(255) USING maker::text"
            )
        )
        conn.execute(text("DROP TYPE IF EXISTS maker"))
    print("Done: shots.maker converted to VARCHAR(255).")


if __name__ == "__main__":
    main()
