#!/usr/bin/env python
"""One-shot script to create all database tables against the real PostgreSQL instance."""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import load_config
from coffee_records.database import Base, get_engine, get_session, init_db

# Import all models so they are registered with Base
import coffee_records.models  # noqa: F401
from coffee_records.models.settings import ShotDefaults


def _seed_defaults() -> None:
    """Insert the shot_defaults singleton row if it doesn't exist yet."""
    with get_session() as session:
        if session.get(ShotDefaults, 1) is None:
            session.add(
                ShotDefaults(
                    id=1,
                    maker="Scott",
                    dose_weight=20.0,
                    pre_infusion_time="5+5",
                    extraction_time=28.0,
                    final_weight=40.0,
                    drink_type="americano",
                    grinder_temp_before=64.0,
                    wedge=True,
                    shaker=True,
                    wdt=True,
                    flow_taper=False,
                )
            )
            session.commit()
            print("Seeded shot_defaults with default values.")
        else:
            print("shot_defaults already present, skipping seed.")


def main() -> None:
    """Create all tables and seed initial data."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables created successfully:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")
    _seed_defaults()


if __name__ == "__main__":
    main()
