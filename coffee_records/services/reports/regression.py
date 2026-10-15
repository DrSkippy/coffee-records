"""Per-coffee bivariate regression of grind setting on bean age and grinder temperature."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
from sqlalchemy.orm import Session

from coffee_records.config import GrindersConfig, GrindModelConfig
from coffee_records.errors import (
    CoffeeNotFoundError,
    InsufficientDataError,
    NoRoastDateError,
)
from coffee_records.models.coffee import Coffee
from coffee_records.models.equipment import Grinder
from coffee_records.models.shot import Shot
from coffee_records.schemas.reports import (
    GrinderRegression,
    GrindRegressionResponse,
    RegressionCoefficients,
    RegressionPoint,
)
from coffee_records.services.grind_notation import (
    GrinderFamily,
    classify_grinder,
    format_grind_numeric,
    parse_grind_numeric,
)
from coffee_records.services.reports.target_time import target_shot_time_wma
from coffee_records.services.stats import FloatArray, r_squared

logger = logging.getLogger(__name__)

# Number of fitted parameters (a, b, c); fewer independent columns is singular.
_N_PARAMETERS = 3


@dataclass(frozen=True)
class RegressionFit:
    """Least-squares fit of ``y = a*x1 + b*x2 + c``.

    Attributes:
        a: Coefficient on x1 (days since roast).
        b: Coefficient on x2 (grinder temperature offset).
        c: Intercept.
        predictions: Fitted y for each input row.
        r_squared: Coefficient of determination (None if y is constant).
    """

    a: float
    b: float
    c: float
    predictions: FloatArray
    r_squared: float | None


def fit_bivariate(
    x1: FloatArray, x2: FloatArray, y: FloatArray
) -> RegressionFit | None:
    """Ordinary least squares for ``y = a*x1 + b*x2 + c``.

    Args:
        x1: First regressor.
        x2: Second regressor.
        y: Response.

    Returns:
        The fit, or None when the design matrix is rank-deficient (e.g. a
        regressor is constant), matching the old singular-matrix skip.
    """
    design = np.column_stack([x1, x2, np.ones_like(x1)])
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank < _N_PARAMETERS:
        return None
    predictions = design @ coefficients
    a, b, c = (float(value) for value in coefficients)
    return RegressionFit(a, b, c, predictions, r_squared(y, predictions))


def _default_grinder_id(session: Session, grinders: GrindersConfig) -> int | None:
    """Return the first dual-scale (Mazzer-style) grinder's id, if any.

    Args:
        session: SQLAlchemy session.
        grinders: Grinder keyword settings.

    Returns:
        Grinder id or None.
    """
    for grinder in session.query(Grinder).order_by(Grinder.id):
        if (
            classify_grinder(grinder.make, grinder.model, grinders)
            is GrinderFamily.DUAL_SCALE
        ):
            logger.debug("grind_regression: defaulting to grinder id=%d", grinder.id)
            return grinder.id
    return None


def _grinder_regression(
    grinder: Grinder | None,
    grinder_id: int,
    points: list[tuple[Shot, float]],
    roast_date: date,
    params: GrindModelConfig,
    grinders: GrindersConfig,
) -> GrinderRegression | None:
    """Fit and package the regression for one grinder's shots.

    Args:
        grinder: Grinder row (None if deleted), used for the label.
        grinder_id: Grinder id.
        points: ``(shot, numeric grind)`` pairs for this grinder (the query
            guarantees grinder_temp_before is set).
        roast_date: The coffee's roast date.
        params: Calibration (reference temperature).
        grinders: Notation settings for formatting.

    Returns:
        The grinder's regression, or None if the fit is singular.
    """
    shots = [shot for shot, _ in points]
    x1 = np.array([(s.date - roast_date).days for s in shots], dtype=float)
    x2 = np.array(
        [cast(float, s.grinder_temp_before) - params.reference_temp_f for s in shots]
    )
    y = np.array([grind for _, grind in points])

    fit = fit_bivariate(x1, x2, y)
    if fit is None:
        logger.warning(
            "grind_regression: singular matrix for grinder_id=%d — skipping", grinder_id
        )
        return None

    return GrinderRegression(
        grinder_id=grinder_id,
        grinder_label=(
            f"{grinder.make} {grinder.model}" if grinder else str(grinder_id)
        ),
        n_shots=len(points),
        coefficients=RegressionCoefficients(
            a=round(fit.a, 6), b=round(fit.b, 6), c=round(fit.c, 6)
        ),
        r_squared=fit.r_squared,
        points=[
            RegressionPoint(
                shot_id=shot.id,
                date=shot.date,
                x1=int(days),
                x2=round(float(temp_offset), 2),
                y=round(float(grind), 4),
                y_str=format_grind_numeric(float(grind), grinders),
                y_predicted=round(float(predicted), 4),
                y_predicted_str=format_grind_numeric(float(predicted), grinders),
            )
            for shot, days, temp_offset, grind, predicted in zip(
                shots, x1, x2, y, fit.predictions
            )
        ],
    )


def grind_regression(
    session: Session,
    coffee_id: int,
    grinder_id: int | None = None,
    params: GrindModelConfig | None = None,
    grinders: GrindersConfig | None = None,
) -> GrindRegressionResponse:
    """Fit a bivariate linear regression to grind settings for a coffee bag.

    Model: y = a*x1 + b*x2 + c
      y  = grind setting (numeric)
      x1 = days since roast
      x2 = grinder_temp_before - reference_temp_f

    Only shots from the same grinder are regressed together.  If grinder_id
    is omitted, the first dual-scale (Mazzer) grinder is used as the default.

    Args:
        session: SQLAlchemy session.
        coffee_id: Coffee primary key.
        grinder_id: Optional grinder filter.  Defaults to Mazzer.
        params: Calibration (defaults to built-in settings).
        grinders: Grinder notation settings (defaults to built-in settings).

    Returns:
        Coffee id, roast date, per-grinder regression results and the
        coffee's target shot time.

    Raises:
        CoffeeNotFoundError: If the coffee does not exist.
        NoRoastDateError: If the coffee has no roast date.
        InsufficientDataError: If no grinder has enough non-singular data.
    """
    params = params or GrindModelConfig()
    grinders = grinders or GrindersConfig()
    coffee = session.get(Coffee, coffee_id)
    if coffee is None:
        raise CoffeeNotFoundError()
    if coffee.roast_date is None:
        raise NoRoastDateError()
    roast_date = coffee.roast_date

    resolved_grinder_id = (
        grinder_id if grinder_id is not None else _default_grinder_id(session, grinders)
    )

    query = session.query(Shot).filter(
        Shot.coffee_id == coffee_id,
        Shot.grind_setting.isnot(None),
        Shot.grinder_temp_before.isnot(None),
        Shot.grinder_id.isnot(None),
    )
    if resolved_grinder_id is not None:
        query = query.filter(Shot.grinder_id == resolved_grinder_id)

    # Group by grinder_id; parse grind setting
    groups: dict[int, list[tuple[Shot, float]]] = defaultdict(list)
    for shot in query.order_by(Shot.date):
        grind = parse_grind_numeric(shot.grind_setting or "")
        if grind is not None and shot.grinder_id is not None:
            groups[shot.grinder_id].append((shot, grind))

    usable = {gid: pts for gid, pts in groups.items() if len(pts) >= params.min_points}
    insufficient = InsufficientDataError(
        f"fewer than {params.min_points} usable data points"
    )
    if not usable:
        raise insufficient

    grinder_rows = {
        g.id: g for g in session.query(Grinder).filter(Grinder.id.in_(usable))
    }
    results = [
        regression
        for gid, pts in usable.items()
        if (
            regression := _grinder_regression(
                grinder_rows.get(gid), gid, pts, roast_date, params, grinders
            )
        )
        is not None
    ]
    if not results:
        raise insufficient

    # Target shot time: weighted moving average of (extraction_time + extraction_delta)
    # across all espresso-based shots for this coffee (recent shots weighted higher).
    target_shot_time, _ = target_shot_time_wma(session, coffee_id, params=params)

    return GrindRegressionResponse(
        coffee_id=coffee_id,
        roast_date=roast_date,
        grinders=results,
        target_shot_time=target_shot_time,
    )
