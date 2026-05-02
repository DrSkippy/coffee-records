#!/usr/bin/env python
"""Migration: create shot_defaults table and seed with current hardcoded values."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from coffee_records.config import load_config
from coffee_records.database import get_engine, init_db


def main() -> None:
    """Create shot_defaults singleton table and seed it if empty."""
    config = load_config()
    db_url = config.database.get_url()
    print(
        f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}"
    )
    init_db(db_url, pool_size=1)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS shot_defaults (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    maker VARCHAR(255) NOT NULL DEFAULT 'Scott',
                    dose_weight FLOAT,
                    pre_infusion_time VARCHAR(50),
                    extraction_time FLOAT,
                    final_weight FLOAT,
                    drink_type VARCHAR(50),
                    grinder_temp_before FLOAT,
                    wedge BOOLEAN NOT NULL DEFAULT false,
                    shaker BOOLEAN NOT NULL DEFAULT false,
                    wdt BOOLEAN NOT NULL DEFAULT false,
                    flow_taper BOOLEAN NOT NULL DEFAULT false,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO shot_defaults
                    (id, maker, dose_weight, pre_infusion_time, extraction_time,
                     final_weight, drink_type, grinder_temp_before,
                     wedge, shaker, wdt, flow_taper)
                VALUES
                    (1, 'Scott', 20, '5+5', 28, 40, 'americano', 64, true, true, true, false)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
    print("Done: shot_defaults table created and seeded.")


if __name__ == "__main__":
    main()
