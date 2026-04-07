#!/usr/bin/env python
"""Migration: add extraction_delta column to shots table and backfill from notes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from coffee_records.config import load_config
from coffee_records.database import get_engine, init_db


def main() -> None:
    """Add extraction_delta column and backfill existing rows."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE shots ADD COLUMN IF NOT EXISTS extraction_delta FLOAT DEFAULT 0"
            )
        )
        conn.execute(
            text("UPDATE shots SET extraction_delta = 0 WHERE extraction_delta IS NULL")
        )
        # Over-extracted → shorter shot → negative delta
        conn.execute(
            text(
                "UPDATE shots SET extraction_delta = -5"
                " WHERE (LOWER(notes) LIKE '%over extracted%'"
                "     OR LOWER(notes) LIKE '%over-extracted%'"
                "     OR LOWER(notes) LIKE '%overextracted%')"
            )
        )
        # Under-extracted → longer shot → positive delta (applied second to take precedence)
        conn.execute(
            text(
                "UPDATE shots SET extraction_delta = 5"
                " WHERE (LOWER(notes) LIKE '%under extracted%'"
                "     OR LOWER(notes) LIKE '%under-extracted%'"
                "     OR LOWER(notes) LIKE '%underextracted%')"
            )
        )
    print("Done: extraction_delta column added and backfilled.")


if __name__ == "__main__":
    main()
