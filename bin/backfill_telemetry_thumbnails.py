#!/usr/bin/env python
"""Generate missing PNG thumbnails for stored shot telemetry."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import Config, load_config  # noqa: E402
from coffee_records.database import get_session, init_db  # noqa: E402
from coffee_records.models.shot import Shot  # noqa: E402
from coffee_records.services.telemetry import (  # noqa: E402
    TelemetryValidationError,
    render_telemetry_thumbnail,
)

logger = logging.getLogger(__name__)


def backfill(config: Config, force: bool = False) -> tuple[int, int, int]:
    """Generate missing thumbnails and return generated, skipped, failed counts."""
    telemetry_dir = Path(config.uploads.coffee_image_dir) / "telemetry"
    generated = skipped = failed = 0
    with get_session() as session:
        filenames = session.query(Shot.telemetry_filename).filter(
            Shot.telemetry_filename.is_not(None)
        )
        for (filename,) in filenames:
            if not filename:
                continue
            json_path = telemetry_dir / filename
            thumbnail_path = json_path.with_suffix(".png")
            if thumbnail_path.exists() and not force:
                skipped += 1
                continue
            try:
                thumbnail = render_telemetry_thumbnail(json_path.read_bytes())
                temp_path = thumbnail_path.with_suffix(".png.tmp")
                temp_path.write_bytes(thumbnail)
                temp_path.replace(thumbnail_path)
                generated += 1
            except (OSError, TelemetryValidationError) as exc:
                logger.error("Could not generate %s: %s", thumbnail_path.name, exc)
                failed += 1
    return generated, skipped, failed


def main() -> None:
    """Run the telemetry thumbnail backfill against the configured database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Replace existing thumbnails"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = load_config()
    init_db(config.database.get_url(), pool_size=1)
    generated, skipped, failed = backfill(config, force=args.force)
    logger.info("Generated %d, skipped %d, failed %d", generated, skipped, failed)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
