"""Train, persist and retrieve the multivariate grind model."""

import logging
from collections.abc import Collection
from datetime import date, datetime, time, timezone

import numpy as np
from sqlalchemy.orm import Session, joinedload

from coffee_records.config import GrindersConfig, GrindModelConfig
from coffee_records.errors import (
    GrinderNotFoundError,
    InsufficientDataError,
    NoTrainingError,
)
from coffee_records.models.coffee import Coffee
from coffee_records.models.equipment import Grinder
from coffee_records.models.grind_model import (
    GrindModelCoffeeIntercept,
    GrindModelTraining,
)
from coffee_records.schemas.grind_model import (
    CoffeeInterceptItem,
    GrindModelParamsResponse,
    GrindModelPoint,
    GrindModelTrainingResponse,
    TargetTimeItem,
)
from coffee_records.services.grind_model.eligibility import split_by_profiling
from coffee_records.services.grind_model.estimator import fit_within_coffee
from coffee_records.services.grind_model.features import (
    COEFFICIENT_NAMES,
    build_feature_rows,
    first_date_per_coffee,
    load_eligible_shots,
)
from coffee_records.services.grind_notation import format_grind_numeric
from coffee_records.services.reports.target_time import target_shot_times_wma

logger = logging.getLogger(__name__)

# Stored coefficients and intercepts are rounded to this many decimals.
_STORED_DECIMALS = 8
# Projected grind values in plotting points are rounded to this many decimals.
_POINT_DECIMALS = 4
# The within-coffee estimator is closed-form: one pass, always converged.
# These fields are kept for compatibility with the earlier iterative fit.
_N_ITERATIONS = 1
_CONVERGED = True


def _get_grinder(session: Session, grinder_id: int) -> Grinder:
    """Load a grinder or raise GrinderNotFoundError.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder primary key.

    Returns:
        The grinder.

    Raises:
        GrinderNotFoundError: If it does not exist.
    """
    grinder = session.get(Grinder, grinder_id)
    if grinder is None:
        raise GrinderNotFoundError()
    return grinder


def _coffee_names(session: Session, coffee_ids: Collection[int]) -> dict[int, str]:
    """Return names for the given coffee ids.

    Args:
        session: SQLAlchemy session.
        coffee_ids: Coffees to look up.

    Returns:
        Mapping of coffee id to name.
    """
    return {
        coffee.id: coffee.name
        for coffee in session.query(Coffee).filter(Coffee.id.in_(coffee_ids))
    }


def _persist_training(
    session: Session,
    training: GrindModelTraining,
    intercepts: dict[int, float],
) -> None:
    """Save a training run and its per-coffee intercepts.

    Args:
        session: SQLAlchemy session (committed here).
        training: New training row.
        intercepts: Rounded intercept per coffee id.
    """
    session.add(training)
    session.flush()
    session.add_all(
        GrindModelCoffeeIntercept(
            training_id=training.id, coffee_id=coffee_id, intercept=intercept
        )
        for coffee_id, intercept in intercepts.items()
    )
    session.commit()


def _training_response(
    training: GrindModelTraining,
    grinder: Grinder,
    intercepts: dict[int, float],
    coffee_names: dict[int, str],
) -> GrindModelTrainingResponse:
    """Build the API response for a training run.

    Args:
        training: Persisted training row.
        grinder: Its grinder.
        intercepts: Intercept per coffee id, in display order.
        coffee_names: Name per coffee id.

    Returns:
        GrindModelTrainingResponse.
    """
    return GrindModelTrainingResponse(
        training_id=training.id,
        grinder_id=grinder.id,
        grinder_label=f"{grinder.make} {grinder.model}",
        trained_at=training.trained_at,
        n_shots_available=training.n_shots_available,
        n_shots_used=training.n_shots_used,
        n_coffees=training.n_coffees,
        n_iterations=training.n_iterations,
        converged=training.converged,
        r_squared=training.r_squared,
        a0=training.a0,
        a2=training.a2,
        a3=training.a3,
        a4=training.a4,
        a5=training.a5,
        coffee_intercepts=[
            CoffeeInterceptItem(
                coffee_id=coffee_id,
                coffee_name=coffee_names.get(coffee_id),
                intercept=intercept,
            )
            for coffee_id, intercept in intercepts.items()
        ],
    )


def fit_grind_model(
    session: Session,
    grinder_id: int,
    params: GrindModelConfig | None = None,
) -> GrindModelTrainingResponse:
    """Fit the multivariate grind model for a grinder and persist it.

    Model (a1 = 1, grind_setting is the OLS dependent variable)::

        grind_setting = a0*(temp - T_ref) + a2*(extraction_time - target_time)
                      + a3*(dose - D_ref) + a4*age_days
                      + a5*(yield - ratio*dose) + c(coffee_id)

    where ``T_ref``, ``D_ref`` and ``ratio`` come from the ``grind_model``
    config block and ``target_time`` is each coffee's weighted moving average
    shot time on this grinder.

    Fitting uses the closed-form within-coffee (fixed effects) estimator: the
    global coefficients are fitted on data demeaned within each coffee, then
    each coffee's intercept ``c`` is its mean residual. Features with too
    little within-coffee variation are held at 0 (see fit_within_coffee).

    Each coffee's first day of shots (dialing in) is excluded, and so are
    shots pulled with shot profiling (see grind_model.eligibility). The
    profiling filter is applied after the dialing-in day is determined from
    all of the coffee's shots, and the eligible/excluded counts are logged.
    ``n_shots_available`` counts every candidate shot, including profiled
    ones, so ``n_shots_used`` reflects all exclusions.

    Persists the result to grind_model_trainings + grind_model_coffee_intercepts.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder to fit for.
        params: Calibration (defaults to built-in settings).

    Returns:
        The persisted training run.

    Raises:
        GrinderNotFoundError: If the grinder does not exist.
        InsufficientDataError: If fewer than ``min_points`` shots are usable.
    """
    params = params or GrindModelConfig()
    grinder = _get_grinder(session, grinder_id)

    shots = load_eligible_shots(session, grinder_id, params)
    coffee_ids = {s.coffee_id for s in shots if s.coffee_id is not None}
    target_times = target_shot_times_wma(session, coffee_ids, grinder_id, params)
    split = split_by_profiling(shots)
    logger.info(
        "fit_grind_model: grinder_id=%d — %d candidate shots: %d eligible,"
        " %d excluded as profiled, %d excluded with unknown profiling flag",
        grinder_id,
        len(shots),
        len(split.eligible),
        len(split.profiled),
        len(split.unknown),
    )
    rows = build_feature_rows(
        split.eligible, target_times, params, first_date_per_coffee(shots)
    )
    if len(rows) < params.min_points:
        raise InsufficientDataError(
            f"fewer than {params.min_points} usable shots after filtering"
        )

    unique_coffees = sorted({row.coffee_id for row in rows})
    coffee_index = {cid: i for i, cid in enumerate(unique_coffees)}
    fit = fit_within_coffee(
        features=np.array([row.features for row in rows], dtype=float),
        y=np.array([row.grind for row in rows], dtype=float),
        groups=np.array([coffee_index[row.coffee_id] for row in rows]),
        min_within_range=params.min_within_coffee_range,
    )

    inactive = [i for i, ok in enumerate(fit.active) if not ok]
    if inactive:
        logger.info(
            "fit_grind_model: grinder_id=%d — zeroing features with insufficient"
            " within-coffee range: indices %s (within_ranges=%s)",
            grinder_id,
            inactive,
            [round(float(fit.within_ranges[i]), 4) for i in inactive],
        )

    coefficients = {
        name: round(float(value), _STORED_DECIMALS)
        for name, value in zip(COEFFICIENT_NAMES, fit.coefficients)
    }
    intercepts = {
        cid: round(float(fit.intercepts[i]), _STORED_DECIMALS)
        for i, cid in enumerate(unique_coffees)
    }
    training = GrindModelTraining(
        grinder_id=grinder_id,
        trained_at=datetime.now(tz=timezone.utc),
        n_shots_available=len(shots),
        n_shots_used=len(rows),
        n_coffees=len(unique_coffees),
        n_iterations=_N_ITERATIONS,
        converged=_CONVERGED,
        r_squared=fit.r_squared,
        **coefficients,
    )
    _persist_training(session, training, intercepts)
    return _training_response(
        training, grinder, intercepts, _coffee_names(session, unique_coffees)
    )


def _load_training(
    session: Session,
    grinder_id: int,
    training_id: int | None,
    as_of: date | None,
) -> GrindModelTraining:
    """Select a training run for a grinder.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder whose trainings to search.
        training_id: Specific run to load, if given.
        as_of: Latest run trained on or before this date (ignored with training_id).

    Returns:
        The matching (most recent) training run.

    Raises:
        NoTrainingError: If nothing matches.
    """
    query = (
        session.query(GrindModelTraining)
        .options(joinedload(GrindModelTraining.coffee_intercepts))
        .filter(GrindModelTraining.grinder_id == grinder_id)
    )
    if training_id is not None:
        query = query.filter(GrindModelTraining.id == training_id)
    elif as_of is not None:
        cutoff = datetime.combine(as_of, time(23, 59, 59), tzinfo=timezone.utc)
        query = query.filter(GrindModelTraining.trained_at <= cutoff)
    training = query.order_by(GrindModelTraining.trained_at.desc()).first()
    if training is None:
        raise NoTrainingError()
    return training


def get_grind_model_params(
    session: Session,
    grinder_id: int,
    training_id: int | None = None,
    as_of: date | None = None,
    params: GrindModelConfig | None = None,
    grinders: GrindersConfig | None = None,
) -> GrindModelParamsResponse:
    """Load grind model parameters and projected data points for plotting.

    Args:
        session: SQLAlchemy session.
        grinder_id: Required — restricts to trainings for this grinder.
        training_id: If given, load this specific training run.
        as_of: If given, load the most recent training whose trained_at date
               is on or before this date.  Ignored if training_id is given.
               Defaults to the most recent training.
        params: Calibration (defaults to built-in settings).
        grinders: Grinder notation settings (defaults to built-in settings).

    Returns:
        The training run plus data points and per-coffee target shot times
        for the shot planner.

    Raises:
        GrinderNotFoundError: If the grinder does not exist.
        NoTrainingError: If no matching training exists.
    """
    params = params or GrindModelConfig()
    grinder = _get_grinder(session, grinder_id)
    training = _load_training(session, grinder_id, training_id, as_of)

    intercepts = {
        item.coffee_id: item.intercept
        for item in sorted(training.coffee_intercepts, key=lambda i: i.coffee_id)
    }
    target_times = target_shot_times_wma(session, intercepts, grinder_id, params)

    # Re-query shots for plotting (all current qualifying shots for coffees in
    # model), with the same profiling filter as training.
    shots = load_eligible_shots(session, grinder_id, params, coffee_ids=intercepts)
    eligible = split_by_profiling(shots).eligible
    coefficients = [float(getattr(training, name)) for name in COEFFICIENT_NAMES]
    points = []
    for row in build_feature_rows(
        eligible, target_times, params, first_date_per_coffee(shots)
    ):
        predicted = (
            sum(a * x for a, x in zip(coefficients, row.features))
            + intercepts[row.coffee_id]
        )
        points.append(
            GrindModelPoint(
                shot_id=row.shot.id,
                date=row.shot.date.isoformat(),
                age_days=row.age_days,
                temp_offset=round(row.temp_offset, 2),
                grind=round(row.grind, _POINT_DECIMALS),
                grind_str=format_grind_numeric(row.grind, grinders),
                grind_predicted=round(predicted, _POINT_DECIMALS),
                grind_predicted_str=format_grind_numeric(predicted, grinders),
            )
        )

    base = _training_response(
        training, grinder, intercepts, _coffee_names(session, intercepts)
    )
    return GrindModelParamsResponse(
        **base.model_dump(),
        points=points,
        target_times=[
            TargetTimeItem(coffee_id=cid, target_shot_time=target_times[cid])
            for cid in intercepts
        ],
    )
