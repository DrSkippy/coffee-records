"""Trend and summary reports over shots."""

from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import func
from sqlalchemy.orm import Session

from coffee_records.models.equipment import BrewingDevice, Grinder
from coffee_records.models.shot import Shot
from coffee_records.schemas.reports import (
    ByCoffeeReport,
    CoffeeShotSummary,
    DoseYieldPoint,
    ExtractionPoint,
    GrinderShotCount,
    ShotsPerDayPoint,
)
from coffee_records.services.reports.filters import ShotFilter, equipment_label

# Ratios and averages are reported to this many decimal places.
_DECIMALS = 3


def _mean(values: Sequence[float]) -> float | None:
    """Return the rounded arithmetic mean, or None for no values.

    Args:
        values: Numbers to average.

    Returns:
        Mean rounded to three decimals, or None.
    """
    return round(sum(values) / len(values), _DECIMALS) if values else None


def dose_yield_over_time(
    session: Session, shot_filter: ShotFilter
) -> list[DoseYieldPoint]:
    """Return dose weight vs final weight ratio per shot over time.

    Args:
        session: SQLAlchemy session.
        shot_filter: Date range (both ends set) and optional id filters.

    Returns:
        One point per shot with both weights recorded, oldest first.
    """
    query = (
        session.query(
            Shot.date,
            Shot.id,
            Shot.dose_weight,
            Shot.final_weight,
            Shot.device_id,
            BrewingDevice.make,
            BrewingDevice.model,
        )
        .outerjoin(BrewingDevice, Shot.device_id == BrewingDevice.id)
        .filter(Shot.dose_weight.isnot(None), Shot.final_weight.isnot(None))
    )
    rows = shot_filter.apply(query).order_by(Shot.date).all()
    return [
        DoseYieldPoint(
            date=row.date,
            shot_id=row.id,
            dose_weight=row.dose_weight,
            final_weight=row.final_weight,
            ratio=(
                round(row.final_weight / row.dose_weight, _DECIMALS)
                if row.dose_weight
                else None
            ),
            device_id=row.device_id,
            device_label=equipment_label(row.make, row.model),
        )
        for row in rows
    ]


def shots_per_grinder(
    session: Session, shot_filter: ShotFilter
) -> list[GrinderShotCount]:
    """Return shot count grouped by grinder within the date range.

    The filter's grinder_id is ignored (every grinder is reported).

    Args:
        session: SQLAlchemy session.
        shot_filter: Date range (both ends set) and optional coffee/device filters.

    Returns:
        Counts per grinder, sorted descending by count.
    """
    shot_filter = replace(shot_filter, grinder_id=None)
    query = (
        session.query(
            Shot.grinder_id,
            Grinder.make,
            Grinder.model,
            func.count(Shot.id).label("count"),
        )
        .join(Grinder, Shot.grinder_id == Grinder.id)
        .filter(Shot.grinder_id.isnot(None))
    )
    rows = (
        shot_filter.apply(query)
        .group_by(Shot.grinder_id, Grinder.make, Grinder.model)
        .order_by(func.count(Shot.id).desc())
        .all()
    )
    return [
        GrinderShotCount(
            grinder_id=row.grinder_id, make=row.make, model=row.model, count=row.count
        )
        for row in rows
    ]


def shots_per_day(session: Session, shot_filter: ShotFilter) -> list[ShotsPerDayPoint]:
    """Return shot count grouped by date.

    Args:
        session: SQLAlchemy session.
        shot_filter: Date range (both ends set) and optional id filters.

    Returns:
        One point per day with at least one shot, oldest first.
    """
    query = session.query(Shot.date, func.count(Shot.id).label("count"))
    rows = shot_filter.apply(query).group_by(Shot.date).order_by(Shot.date).all()
    return [ShotsPerDayPoint(date=row.date, count=row.count) for row in rows]


def extraction_trends(
    session: Session, shot_filter: ShotFilter
) -> list[ExtractionPoint]:
    """Return extraction time per shot over time.

    Args:
        session: SQLAlchemy session.
        shot_filter: Date range (both ends set) and optional id filters.

    Returns:
        One point per shot with an extraction time, oldest first.
    """
    query = (
        session.query(
            Shot.date,
            Shot.id,
            Shot.extraction_time,
            Shot.device_id,
            BrewingDevice.make,
            BrewingDevice.model,
        )
        .outerjoin(BrewingDevice, Shot.device_id == BrewingDevice.id)
        .filter(Shot.extraction_time.isnot(None))
    )
    rows = shot_filter.apply(query).order_by(Shot.date).all()
    return [
        ExtractionPoint(
            date=row.date,
            shot_id=row.id,
            extraction_time=row.extraction_time,
            device_id=row.device_id,
            device_label=equipment_label(row.make, row.model),
        )
        for row in rows
    ]


def by_coffee(session: Session, shot_filter: ShotFilter) -> ByCoffeeReport:
    """Return stats for all shots using a specific coffee bag.

    Args:
        session: SQLAlchemy session.
        shot_filter: Date range (both ends set) with coffee_id set.

    Returns:
        Shot count, averages of dose/yield/time/ratio, and the shot list.

    Raises:
        ValueError: If the filter has no coffee_id (programming error).
    """
    if shot_filter.coffee_id is None:
        raise ValueError("by_coffee requires shot_filter.coffee_id")
    shots = shot_filter.apply(session.query(Shot)).order_by(Shot.date).all()

    doses = [s.dose_weight for s in shots if s.dose_weight is not None]
    finals = [s.final_weight for s in shots if s.final_weight is not None]
    extractions = [s.extraction_time for s in shots if s.extraction_time is not None]
    ratios = [
        s.final_weight / s.dose_weight
        for s in shots
        if s.final_weight is not None
        and s.dose_weight is not None
        and s.dose_weight > 0
    ]

    return ByCoffeeReport(
        coffee_id=shot_filter.coffee_id,
        total_shots=len(shots),
        avg_dose=_mean(doses),
        avg_final_weight=_mean(finals),
        avg_extraction_time=_mean(extractions),
        avg_ratio=_mean(ratios),
        shots=[
            CoffeeShotSummary(
                date=s.date,
                shot_id=s.id,
                dose_weight=s.dose_weight,
                final_weight=s.final_weight,
                extraction_time=s.extraction_time,
            )
            for s in shots
        ],
    )
