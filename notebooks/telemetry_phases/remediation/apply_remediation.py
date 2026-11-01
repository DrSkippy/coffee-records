"""Apply the approved one-time shot remediation in ``proposal.yaml``.

Dry run by default: prints what would change. With ``--apply`` it first
writes the current values to ``backup_<timestamp>.csv`` (for rollback),
then updates each ``recommend: true`` change whose current database value
still matches the proposal, and appends an audit line to the shot's notes.

Usage (repo root, ``.envrc`` loaded)::

    poetry run python notebooks/telemetry_phases/remediation/apply_remediation.py
    poetry run python notebooks/telemetry_phases/remediation/apply_remediation.py --apply
"""

import argparse
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from coffee_records.config import load_config
from coffee_records.database import get_session, init_db
from coffee_records.models.shot import Shot

HERE = Path(__file__).resolve().parent
FIELDS = ("extraction_time", "flow_taper")
logger = logging.getLogger("remediation")


def main() -> None:
    """Dry-run or apply the approved changes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=HERE / "proposal.yaml")
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    doc: dict[str, Any] = yaml.safe_load(args.proposal.read_text())
    approved = [c for c in doc["changes"] if c["recommend"]]
    if any(c["field"] not in FIELDS for c in approved):
        raise SystemExit(f"Only {FIELDS} can be remediated")

    config = load_config()
    init_db(config.database.get_url())
    with get_session() as session:
        shots = {
            s.id: s
            for s in session.query(Shot).filter(
                Shot.id.in_({c["shot_id"] for c in approved})
            )
        }
        stale = [
            c
            for c in approved
            if c["shot_id"] not in shots
            or getattr(shots[c["shot_id"]], c["field"]) != c["current"]
        ]
        if stale:
            for c in stale:
                logger.error(
                    "Stale: shot %s %s changed since the proposal",
                    c["shot_id"],
                    c["field"],
                )
            raise SystemExit("Database differs from the proposal; nothing applied")

        if args.apply:
            backup = HERE / f"backup_{datetime.now():%Y%m%dT%H%M%S}.csv"
            with backup.open("w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["shot_id", "field", "value", "notes"])
                for c in approved:
                    shot = shots[c["shot_id"]]
                    writer.writerow(
                        [shot.id, c["field"], c["current"], shot.notes or ""]
                    )
            logger.info("Backed up current values to %s", backup)

        for c in approved:
            shot = shots[c["shot_id"]]
            line = doc["note_suffix"].format(**c)
            logger.info(
                "%s shot %s: %s %s -> %s",
                "Apply" if args.apply else "Would apply",
                shot.id,
                c["field"],
                c["current"],
                c["proposed"],
            )
            if args.apply:
                setattr(shot, c["field"], c["proposed"])
                shot.notes = f"{shot.notes}\n\n{line}" if shot.notes else line
        if args.apply:
            session.commit()
            logger.info("Applied %d changes", len(approved))
        else:
            logger.info(
                "Dry run: %d changes; re-run with --apply to write", len(approved)
            )


if __name__ == "__main__":
    main()
