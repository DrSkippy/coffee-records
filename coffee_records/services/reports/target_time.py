"""Weighted moving average target shot times."""

from collections import defaultdict
from collections.abc import Collection, Sequence

from sqlalchemy.orm import Session

from coffee_records.config import GrindModelConfig
from coffee_records.models.shot import Shot


def weighted_moving_average(values: Sequence[float]) -> float | None:
    """Linearly weighted mean, oldest first, rounded to one decimal.

    Formula: wma = Σ(i+1)·vᵢ / Σ(i+1), where the denominator is N(N+1)/2.

    Args:
        values: Values ordered oldest (i=0) to most recent (i=N-1).

    Returns:
        The rounded average, or None for an empty sequence.
    """
    if not values:
        return None
    weighted_sum = sum((i + 1) * value for i, value in enumerate(values))
    n = len(values)
    return round(weighted_sum / (n * (n + 1) / 2), 1)


def _shot_times_by_coffee(
    session: Session,
    coffee_ids: Collection[int],
    grinder_id: int | None,
    device_id: int | None,
    params: GrindModelConfig,
) -> dict[int, list[float]]:
    """Load (extraction_time + extraction_delta) per coffee, oldest first.

    Args:
        session: SQLAlchemy session.
        coffee_ids: Coffees to include.
        grinder_id: Optional grinder filter.
        device_id: Optional brewing device filter.
        params: Supplies the espresso drink types.

    Returns:
        Mapping of coffee id to its ordered effective shot times.
    """
    query = session.query(
        Shot.coffee_id, Shot.extraction_time, Shot.extraction_delta
    ).filter(
        Shot.coffee_id.in_(coffee_ids),
        Shot.extraction_time.isnot(None),
        Shot.drink_type.in_(params.espresso_drink_types),
    )
    if grinder_id is not None:
        query = query.filter(Shot.grinder_id == grinder_id)
    if device_id is not None:
        query = query.filter(Shot.device_id == device_id)

    times: dict[int, list[float]] = defaultdict(list)
    for coffee_id, extraction_time, delta in query.order_by(
        Shot.date.asc(), Shot.created_at.asc()
    ):
        times[coffee_id].append(extraction_time + (delta or 0.0))
    return times


def target_shot_time_wma(
    session: Session,
    coffee_id: int,
    grinder_id: int | None = None,
    device_id: int | None = None,
    params: GrindModelConfig | None = None,
) -> tuple[float | None, int]:
    """Weighted moving average of (extraction_time + extraction_delta) for espresso shots.

    Shots are ordered oldest-first (i=0) to most recent (i=N-1), giving higher
    weight to recent shots.  Formula: wma = Σ(i+1)(tᵢ+dtᵢ) / Σ(i+1) where
    the denominator equals N*(N+1)/2.

    Args:
        session: SQLAlchemy session.
        coffee_id: Filter to shots for this coffee bag.
        grinder_id: Optional filter by grinder.
        device_id: Optional filter by brewing device.
        params: Supplies the espresso drink types (defaults to built-in settings).

    Returns:
        Tuple of (wma rounded to 1 decimal place, shot count used).
        wma is None when no qualifying shots exist.
    """
    params = params or GrindModelConfig()
    times = _shot_times_by_coffee(
        session, [coffee_id], grinder_id, device_id, params
    ).get(coffee_id, [])
    return weighted_moving_average(times), len(times)


def target_shot_times_wma(
    session: Session,
    coffee_ids: Collection[int],
    grinder_id: int | None = None,
    params: GrindModelConfig | None = None,
) -> dict[int, float | None]:
    """Batch version of target_shot_time_wma: one query for many coffees.

    Args:
        session: SQLAlchemy session.
        coffee_ids: Coffees to compute targets for.
        grinder_id: Optional filter by grinder.
        params: Supplies the espresso drink types (defaults to built-in settings).

    Returns:
        Mapping of every requested coffee id to its WMA (None if no shots).
    """
    params = params or GrindModelConfig()
    times = _shot_times_by_coffee(session, coffee_ids, grinder_id, None, params)
    return {cid: weighted_moving_average(times.get(cid, [])) for cid in coffee_ids}
