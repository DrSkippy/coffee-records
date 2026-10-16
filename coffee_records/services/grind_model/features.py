"""Shot loading and feature construction shared by grind model training and plotting."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

from sqlalchemy.orm import Session, joinedload

from coffee_records.config import GrindModelConfig
from coffee_records.models.coffee import Coffee
from coffee_records.models.shot import Shot
from coffee_records.services.grind_notation import parse_grind_numeric

# Persisted coefficient name for each feature, in feature order. (a1 is the
# implicit unit coefficient on the grind setting itself, so it is absent.)
COEFFICIENT_NAMES = ("a0", "a2", "a3", "a4", "a5")


@dataclass(frozen=True)
class FeatureRow:
    """One training shot projected into model features.

    Attributes:
        shot: Source shot.
        coffee_id: Shot's coffee (fixed-effect group).
        age_days: Days between roast and shot.
        grind: Numeric grind setting (the dependent variable).
        features: ``(temp offset, extraction time − target, dose offset,
            age_days, yield − ratio·dose)`` in COEFFICIENT_NAMES order.
    """

    shot: Shot
    coffee_id: int
    age_days: int
    grind: float
    features: tuple[float, float, float, float, float]

    @property
    def temp_offset(self) -> float:
        """Grinder temperature minus the reference temperature."""
        return self.features[0]


def load_eligible_shots(
    session: Session,
    grinder_id: int,
    params: GrindModelConfig,
    coffee_ids: Collection[int] | None = None,
) -> list[Shot]:
    """Load all shots eligible for the grind model for a grinder.

    Eligible shots are espresso drinks with grind setting, grinder
    temperature, dose, yield and extraction time recorded, for a coffee
    with a roast date.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder primary key.
        params: Supplies the espresso drink types.
        coffee_ids: Optional restriction to these coffees.

    Returns:
        Shots ordered by date asc, created_at asc, with ``coffee`` loaded.
    """
    query = (
        session.query(Shot)
        .options(joinedload(Shot.coffee))
        .join(Coffee, Shot.coffee_id == Coffee.id)
        .filter(
            Shot.grinder_id == grinder_id,
            Shot.drink_type.in_(params.espresso_drink_types),
            Shot.grind_setting.isnot(None),
            Shot.grinder_temp_before.isnot(None),
            Shot.coffee_id.isnot(None),
            Shot.dose_weight.isnot(None),
            Shot.final_weight.isnot(None),
            Shot.extraction_time.isnot(None),
            Coffee.roast_date.isnot(None),
        )
    )
    if coffee_ids is not None:
        query = query.filter(Shot.coffee_id.in_(coffee_ids))
    return query.order_by(Shot.date.asc(), Shot.created_at.asc()).all()


def first_date_per_coffee(shots: list[Shot]) -> dict[int, date]:
    """Return the earliest shot date for each coffee_id in the list.

    Args:
        shots: List of Shot instances.

    Returns:
        Mapping of coffee_id to earliest date.
    """
    result: dict[int, date] = {}
    for shot in shots:
        cid = shot.coffee_id
        if cid is not None and (cid not in result or shot.date < result[cid]):
            result[cid] = shot.date
    return result


def build_feature_rows(
    shots: list[Shot],
    target_times: Mapping[int, float | None],
    params: GrindModelConfig,
    first_dates: Mapping[int, date] | None = None,
) -> list[FeatureRow]:
    """Project eligible shots into feature rows.

    Skips each coffee's first-day shots (dialing-in), unparseable grind
    settings, and coffees without a target shot time.

    Args:
        shots: Shots to project (e.g. load_eligible_shots after the
            profiling filter).
        target_times: Target shot time per coffee id.
        params: Reference values used to center the features.
        first_dates: Each coffee's dialing-in day. Pass it when ``shots`` is
            a filtered subset so the first day still reflects every shot of
            the coffee; defaults to the earliest date within ``shots``.

    Returns:
        Usable feature rows, in input order.
    """
    if first_dates is None:
        first_dates = first_date_per_coffee(shots)
    rows: list[FeatureRow] = []
    for shot in shots:
        cid = shot.coffee_id
        if cid is None or shot.date == first_dates.get(cid):
            continue
        grind = parse_grind_numeric(shot.grind_setting or "")
        if grind is None:
            continue
        target_time = target_times.get(cid)
        if target_time is None:
            continue
        coffee = shot.coffee
        if coffee is None or coffee.roast_date is None:
            continue
        # load_eligible_shots guarantees these columns are non-null.
        temp = cast(float, shot.grinder_temp_before)
        dose = cast(float, shot.dose_weight)
        final_weight = cast(float, shot.final_weight)
        extraction_time = cast(float, shot.extraction_time)
        age_days = (shot.date - coffee.roast_date).days
        rows.append(
            FeatureRow(
                shot=shot,
                coffee_id=cid,
                age_days=age_days,
                grind=grind,
                features=(
                    float(temp) - params.reference_temp_f,
                    float(extraction_time) - target_time,
                    float(dose) - params.reference_dose_g,
                    float(age_days),
                    float(final_weight) - params.target_brew_ratio * float(dose),
                ),
            )
        )
    return rows
