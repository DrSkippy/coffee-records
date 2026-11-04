#!/usr/bin/env python
"""One-off repair: merge duplicate coffee entries created by OCR import.

For each known duplicate pair, reassigns all shots from the higher-ID duplicate
to the lower-ID keeper, then deletes the duplicate row.

Usage:
    poetry run python bin/repair_duplicate_coffees.py           # dry run (default)
    poetry run python bin/repair_duplicate_coffees.py --apply   # execute changes
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import TypedDict

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import load_config  # noqa: E402
from coffee_records.database import get_session, init_db  # noqa: E402
from coffee_records.models.coffee import Coffee  # noqa: E402
from coffee_records.models.shot import Shot  # noqa: E402

logger = logging.getLogger(__name__)


class DuplicateSpec(TypedDict):
    """Identifies one duplicate coffee cluster."""

    description: str
    roast_date: date
    name_hint: str
    roaster_hint: str


# Each entry identifies a duplicate cluster by roast_date + case-insensitive
# substrings on name and roaster.  The script queries at runtime so no IDs are
# hardcoded — it will still work correctly if earlier coffees are renumbered.
DUPLICATE_SPECS: list[DuplicateSpec] = [
    {
        "description": "Ollancay/Ollancey — Prodigal, roast_date 2026-01-26",
        "roast_date": date(2026, 1, 26),
        "name_hint": "ollanc",  # matches both "Ollancay" and "Ollancey"
        "roaster_hint": "prodigal",
    },
    {
        "description": "Kiangoi AB — Queen City Collective / Queenly Col., roast_date 2026-01-07",
        "roast_date": date(2026, 1, 7),
        "name_hint": "kiangoi",
        "roaster_hint": "queen",
    },
    {
        "description": "Cherry Picker Blend — Boxcar, roast_date 2026-02-10",
        "name_hint": "cherry picker",
        "roast_date": date(2026, 2, 10),
        "roaster_hint": "boxcar",
    },
]


def find_duplicate_pair(
    session: Session,
    roast_date: date,
    name_hint: str,
    roaster_hint: str,
) -> tuple[Coffee, Coffee] | None:
    """Return (keeper, duplicate) sorted by id ascending, or None.

    Args:
        session:      SQLAlchemy session
        roast_date:   Expected roast date for both rows
        name_hint:    Case-insensitive substring to match coffee name
        roaster_hint: Case-insensitive substring to match roaster name

    Returns:
        (keeper, duplicate) tuple where keeper.id < duplicate.id, or None
    """
    rows = (
        session.query(Coffee)
        .filter(
            Coffee.roast_date == roast_date,
            Coffee.name.ilike(f"%{name_hint}%"),
            Coffee.roaster.ilike(f"%{roaster_hint}%"),
        )
        .order_by(Coffee.id)
        .all()
    )
    if len(rows) == 0:
        logger.info(
            "  NOT FOUND: no coffees match roast_date=%s name~=%r roaster~=%r",
            roast_date,
            name_hint,
            roaster_hint,
        )
        return None
    if len(rows) == 1:
        logger.info(
            "  ALREADY CLEAN: only one match — id=%s '%s' / '%s'",
            rows[0].id,
            rows[0].roaster,
            rows[0].name,
        )
        return None
    if len(rows) > 2:
        logger.warning(
            "  WARNING: %d rows matched (expected 2) — skipping, manual review needed:",
            len(rows),
        )
        for r in rows:
            logger.warning("    id=%s  '%s' / '%s'", r.id, r.roaster, r.name)
        return None
    return (rows[0], rows[1])  # keeper (lower id), duplicate (higher id)


def repair_spec(session: Session, spec: DuplicateSpec, dry_run: bool) -> None:
    """Report — and unless ``dry_run``, apply — one duplicate-cluster repair.

    Reassigns all shots from the higher-ID duplicate to the lower-ID keeper
    and deletes the duplicate row. The caller commits.

    Args:
        session: SQLAlchemy session.
        spec: Duplicate cluster to repair.
        dry_run: When True, only report what would change.
    """
    logger.info("--- %s ---", spec["description"])
    pair = find_duplicate_pair(
        session,
        spec["roast_date"],
        spec["name_hint"],
        spec["roaster_hint"],
    )
    if pair is None:
        return

    keeper, duplicate = pair
    logger.info(
        "  KEEPER:    id=%s  '%s' / '%s'", keeper.id, keeper.roaster, keeper.name
    )
    logger.info(
        "  DUPLICATE: id=%s  '%s' / '%s'",
        duplicate.id,
        duplicate.roaster,
        duplicate.name,
    )

    shot_count = session.query(Shot).filter(Shot.coffee_id == duplicate.id).count()
    logger.info("  Shots referencing duplicate: %s", shot_count)
    logger.info(
        "  Will: UPDATE shots SET coffee_id=%s WHERE coffee_id=%s",
        keeper.id,
        duplicate.id,
    )
    logger.info("  Will: DELETE coffees WHERE id=%s", duplicate.id)

    if not dry_run:
        session.query(Shot).filter(Shot.coffee_id == duplicate.id).update(
            {"coffee_id": keeper.id}
        )
        session.delete(duplicate)
        logger.info("  Done.")


def main() -> None:
    """Parse arguments and run the repair."""
    parser = argparse.ArgumentParser(
        description="Repair duplicate coffee entries from OCR import.",
        epilog=(
            "Examples:\n"
            "  poetry run python bin/repair_duplicate_coffees.py\n"
            "  poetry run python bin/repair_duplicate_coffees.py --apply\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute changes. Default is dry-run (report only).",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    init_db(config.database.get_url(), pool_size=1)
    session = get_session()

    if dry_run:
        logger.info(
            "=== DRY RUN — no changes will be written. Pass --apply to execute. ==="
        )
    else:
        logger.info("=== APPLY MODE — changes will be committed. ===")

    try:
        for spec in DUPLICATE_SPECS:
            repair_spec(session, spec, dry_run)

        if not dry_run:
            session.commit()
            logger.info("All changes committed.")
        else:
            logger.info("Dry run complete. Re-run with --apply to execute.")

    except (SQLAlchemyError, ValueError):
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
