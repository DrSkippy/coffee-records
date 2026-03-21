#!/usr/bin/env python
"""Migration: add image_filename column to coffees table."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from coffee_records.config import load_config
from coffee_records.database import get_engine, init_db


def main() -> None:
    """Add image_filename column if it does not already exist."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE coffees ADD COLUMN IF NOT EXISTS image_filename VARCHAR(255)"
            )
        )
    print("Done: image_filename column added to coffees.")


if __name__ == "__main__":
    main()
