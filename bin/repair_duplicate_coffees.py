#!/usr/bin/env python
"""One-off repair: merge duplicate coffee entries created by OCR import.

For each known duplicate pair, reassigns all shots from the higher-ID duplicate
to the lower-ID keeper, then deletes the duplicate row.

Usage:
    poetry run python bin/repair_duplicate_coffees.py           # dry run (default)
    poetry run python bin/repair_duplicate_coffees.py --apply   # execute changes
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import load_config
from coffee_records.database import get_session, init_db
from coffee_records.models.coffee import Coffee
from coffee_records.models.shot import Shot

# Each entry identifies a duplicate cluster by roast_date + case-insensitive
# substrings on name and roaster.  The script queries at runtime so no IDs are
# hardcoded — it will still work correctly if earlier coffees are renumbered.
DUPLICATE_SPECS = [
    {
        "description": "Ollancay/Ollancey — Prodigal, roast_date 2026-01-26",
        "roast_date": date(2026, 1, 26),
        "name_hint": "ollanc",    # matches both "Ollancay" and "Ollancey"
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
        "roast_date": date(2026, 2, 10),
        "name_hint": "cherry picker",
        "roaster_hint": "boxcar",
    },
]


def find_duplicate_pair(
    session,
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
        print(f"  NOT FOUND: no coffees match roast_date={roast_date} name~={name_hint!r} roaster~={roaster_hint!r}")
        return None
    if len(rows) == 1:
        print(f"  ALREADY CLEAN: only one match — id={rows[0].id} '{rows[0].roaster}' / '{rows[0].name}'")
        return None
    if len(rows) > 2:
        print(f"  WARNING: {len(rows)} rows matched (expected 2) — skipping, manual review needed:")
        for r in rows:
            print(f"    id={r.id}  '{r.roaster}' / '{r.name}'")
        return None
    return (rows[0], rows[1])  # keeper (lower id), duplicate (higher id)


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

    config = load_config()
    init_db(config.database.get_url(), pool_size=1)
    session = get_session()

    if dry_run:
        print("=== DRY RUN — no changes will be written. Pass --apply to execute. ===\n")
    else:
        print("=== APPLY MODE — changes will be committed. ===\n")

    try:
        for spec in DUPLICATE_SPECS:
            print(f"--- {spec['description']} ---")
            pair = find_duplicate_pair(
                session,
                spec["roast_date"],
                spec["name_hint"],
                spec["roaster_hint"],
            )
            if pair is None:
                print()
                continue

            keeper, duplicate = pair
            print(f"  KEEPER:    id={keeper.id}  '{keeper.roaster}' / '{keeper.name}'")
            print(f"  DUPLICATE: id={duplicate.id}  '{duplicate.roaster}' / '{duplicate.name}'")

            shot_count = (
                session.query(Shot)
                .filter(Shot.coffee_id == duplicate.id)
                .count()
            )
            print(f"  Shots referencing duplicate: {shot_count}")
            print(f"  Will: UPDATE shots SET coffee_id={keeper.id} WHERE coffee_id={duplicate.id}")
            print(f"  Will: DELETE coffees WHERE id={duplicate.id}")

            if not dry_run:
                session.query(Shot).filter(Shot.coffee_id == duplicate.id).update(
                    {"coffee_id": keeper.id}
                )
                session.delete(duplicate)
                print(f"  Done.")
            print()

        if not dry_run:
            session.commit()
            print("All changes committed.")
        else:
            print("Dry run complete. Re-run with --apply to execute.")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
