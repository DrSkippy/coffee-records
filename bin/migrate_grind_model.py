#!/usr/bin/env python
"""Migration: add aeropress to drinktype enum and create grind model tables.

Safe to run multiple times — uses IF NOT EXISTS and ADD VALUE IF NOT EXISTS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from coffee_records.config import load_config
from coffee_records.database import get_engine, init_db


def main() -> None:
    """Run migration."""
    config = load_config()
    db_url = config.database.get_url()
    print(f"Connecting to: {config.database.host}:{config.database.port}/{config.database.name}")
    init_db(db_url, pool_size=1)
    engine = get_engine()

    with engine.begin() as conn:
        # 1. Add aeropress to the drinktype enum (PostgreSQL only; idempotent)
        conn.execute(text("ALTER TYPE drink_type ADD VALUE IF NOT EXISTS 'aeropress'"))
        print("drinktype enum: added 'aeropress' (or already present)")

        # 2. Create grind_model_trainings
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS grind_model_trainings (
                    id                  SERIAL PRIMARY KEY,
                    grinder_id          INTEGER NOT NULL REFERENCES grinders(id),
                    trained_at          TIMESTAMPTZ NOT NULL,
                    n_shots_available   INTEGER NOT NULL,
                    n_shots_used        INTEGER NOT NULL,
                    n_coffees           INTEGER NOT NULL,
                    n_iterations        INTEGER NOT NULL,
                    converged           BOOLEAN NOT NULL,
                    r_squared           FLOAT,
                    a0                  FLOAT NOT NULL,
                    a2                  FLOAT NOT NULL,
                    a3                  FLOAT NOT NULL,
                    a4                  FLOAT NOT NULL,
                    a5                  FLOAT NOT NULL,
                    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        print("grind_model_trainings: created (or already exists)")

        # 3. Create grind_model_coffee_intercepts
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS grind_model_coffee_intercepts (
                    id          SERIAL PRIMARY KEY,
                    training_id INTEGER NOT NULL REFERENCES grind_model_trainings(id),
                    coffee_id   INTEGER NOT NULL REFERENCES coffees(id),
                    intercept   FLOAT NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        print("grind_model_coffee_intercepts: created (or already exists)")

    print("Migration complete.")


if __name__ == "__main__":
    main()
