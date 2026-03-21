"""Report query logic for trends and statistics."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from coffee_records.models.shot import Shot


def _default_range() -> tuple[date, date]:
    """Return the default 30-day date range (inclusive).

    Returns:
        Tuple of (date_from, date_to).
    """
    today = date.today()
    return today - timedelta(days=30), today


def dose_yield_over_time(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Return dose weight vs final weight ratio per shot over time.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.

    Returns:
        List of dicts with keys: date, shot_id, dose_weight, final_weight, ratio.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    rows = (
        session.query(
            Shot.date,
            Shot.id,
            Shot.dose_weight,
            Shot.final_weight,
        )
        .filter(Shot.date >= date_from, Shot.date <= date_to)
        .filter(Shot.dose_weight.isnot(None), Shot.final_weight.isnot(None))
        .order_by(Shot.date)
        .all()
    )
    results = []
    for row in rows:
        ratio = row.final_weight / row.dose_weight if row.dose_weight else None
        results.append(
            {
                "date": row.date.isoformat(),
                "shot_id": row.id,
                "dose_weight": row.dose_weight,
                "final_weight": row.final_weight,
                "ratio": round(ratio, 3) if ratio is not None else None,
            }
        )
    return results


def shots_per_day(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Return shot count grouped by date.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.

    Returns:
        List of dicts with keys: date, count.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    rows = (
        session.query(Shot.date, func.count(Shot.id).label("count"))
        .filter(Shot.date >= date_from, Shot.date <= date_to)
        .group_by(Shot.date)
        .order_by(Shot.date)
        .all()
    )
    return [{"date": row.date.isoformat(), "count": row.count} for row in rows]


def extraction_trends(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Return extraction time per shot over time.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.

    Returns:
        List of dicts with keys: date, shot_id, extraction_time.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    rows = (
        session.query(Shot.date, Shot.id, Shot.extraction_time)
        .filter(Shot.date >= date_from, Shot.date <= date_to)
        .filter(Shot.extraction_time.isnot(None))
        .order_by(Shot.date)
        .all()
    )
    return [
        {
            "date": row.date.isoformat(),
            "shot_id": row.id,
            "extraction_time": row.extraction_time,
        }
        for row in rows
    ]


def by_coffee(
    session: Session,
    coffee_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Return stats for all shots using a specific coffee bag.

    Args:
        session: SQLAlchemy session.
        coffee_id: Coffee primary key.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.

    Returns:
        Dict with total_shots, avg_dose, avg_final_weight, avg_extraction_time, avg_ratio, shots list.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    rows = (
        session.query(Shot)
        .filter(
            Shot.coffee_id == coffee_id,
            Shot.date >= date_from,
            Shot.date <= date_to,
        )
        .order_by(Shot.date)
        .all()
    )

    doses = [s.dose_weight for s in rows if s.dose_weight is not None]
    finals = [s.final_weight for s in rows if s.final_weight is not None]
    extractions = [s.extraction_time for s in rows if s.extraction_time is not None]
    ratios = [
        s.final_weight / s.dose_weight
        for s in rows
        if s.final_weight is not None and s.dose_weight is not None and s.dose_weight > 0
    ]

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "coffee_id": coffee_id,
        "total_shots": len(rows),
        "avg_dose": avg(doses),
        "avg_final_weight": avg(finals),
        "avg_extraction_time": avg(extractions),
        "avg_ratio": avg(ratios),
        "shots": [
            {
                "date": s.date.isoformat(),
                "shot_id": s.id,
                "dose_weight": s.dose_weight,
                "final_weight": s.final_weight,
                "extraction_time": s.extraction_time,
            }
            for s in rows
        ],
    }
