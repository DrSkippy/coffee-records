"""Reports blueprint — /api/reports/*."""

from datetime import date

from flask import Blueprint, jsonify, request

from coffee_records.database import get_session
from coffee_records.services.reports import (
    by_coffee,
    dose_yield_over_time,
    extraction_trends,
    shots_per_day,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _parse_dates() -> tuple[date | None, date | None]:
    """Parse date_from and date_to query parameters.

    Returns:
        Tuple of (date_from, date_to), either may be None.
    """
    date_from = None
    date_to = None
    if df := request.args.get("date_from"):
        date_from = date.fromisoformat(df)
    if dt := request.args.get("date_to"):
        date_to = date.fromisoformat(dt)
    return date_from, date_to


@reports_bp.get("/dose-yield")
def report_dose_yield() -> object:
    """Dose vs yield ratio over time.

    Returns:
        JSON list of dose/yield data points.
    """
    date_from, date_to = _parse_dates()
    with get_session() as session:
        return jsonify(dose_yield_over_time(session, date_from, date_to))


@reports_bp.get("/shots-per-day")
def report_shots_per_day() -> object:
    """Shot count grouped by date.

    Returns:
        JSON list of date/count pairs.
    """
    date_from, date_to = _parse_dates()
    with get_session() as session:
        return jsonify(shots_per_day(session, date_from, date_to))


@reports_bp.get("/extraction-trends")
def report_extraction_trends() -> object:
    """Extraction time over time.

    Returns:
        JSON list of extraction time data points.
    """
    date_from, date_to = _parse_dates()
    with get_session() as session:
        return jsonify(extraction_trends(session, date_from, date_to))


@reports_bp.get("/by-coffee/<int:coffee_id>")
def report_by_coffee(coffee_id: int) -> object:
    """All stats scoped to one coffee bag.

    Args:
        coffee_id: Coffee primary key.

    Returns:
        JSON dict with aggregate stats and shot list.
    """
    date_from, date_to = _parse_dates()
    with get_session() as session:
        return jsonify(by_coffee(session, coffee_id, date_from, date_to))
