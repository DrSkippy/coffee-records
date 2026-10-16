"""Reports blueprint — /api/reports/*."""

from collections.abc import Sequence
from http import HTTPStatus

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from pydantic import BaseModel

from coffee_records.blueprints.helpers import (
    get_config,
    query_date,
    query_int,
    require_query_int,
)
from coffee_records.database import get_session
from coffee_records.schemas.reports import TargetShotTimeResponse
from coffee_records.services.grind_model import fit_grind_model, get_grind_model_params
from coffee_records.services.reports import (
    ShotFilter,
    by_coffee,
    dose_yield_over_time,
    extraction_trends,
    grind_regression,
    shots_per_day,
    shots_per_grinder,
    target_shot_time_wma,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _shot_filter(*, include_grinder: bool = True) -> ShotFilter:
    """Build a ShotFilter from query parameters, defaulting the date range.

    Args:
        include_grinder: Whether to honour the grinder_id parameter.

    Returns:
        A filter with both dates set.
    """
    return ShotFilter(
        date_from=query_date("date_from"),
        date_to=query_date("date_to"),
        coffee_id=query_int("coffee_id"),
        grinder_id=query_int("grinder_id") if include_grinder else None,
        device_id=query_int("device_id"),
    ).with_default_range(get_config().reports.default_range_days)


def _json_list(items: Sequence[BaseModel]) -> ResponseReturnValue:
    """Serialize a list of Pydantic models as a JSON array.

    Args:
        items: Response models.

    Returns:
        Flask JSON response.
    """
    return jsonify([item.model_dump(mode="json") for item in items])


@reports_bp.get("/dose-yield")
def report_dose_yield() -> ResponseReturnValue:
    """Dose vs yield ratio over time.

    Returns:
        JSON list of dose/yield data points.
    """
    shot_filter = _shot_filter()
    with get_session() as session:
        return _json_list(dose_yield_over_time(session, shot_filter))


@reports_bp.get("/shots-per-day")
def report_shots_per_day() -> ResponseReturnValue:
    """Shot count grouped by date.

    Returns:
        JSON list of date/count pairs.
    """
    shot_filter = _shot_filter()
    with get_session() as session:
        return _json_list(shots_per_day(session, shot_filter))


@reports_bp.get("/extraction-trends")
def report_extraction_trends() -> ResponseReturnValue:
    """Extraction time over time.

    Returns:
        JSON list of extraction time data points.
    """
    shot_filter = _shot_filter()
    with get_session() as session:
        return _json_list(extraction_trends(session, shot_filter))


@reports_bp.get("/shots-per-grinder")
def report_shots_per_grinder() -> ResponseReturnValue:
    """Shot count grouped by grinder.

    Returns:
        JSON list of grinder_id/make/model/count objects, sorted by count descending.
    """
    shot_filter = _shot_filter(include_grinder=False)
    with get_session() as session:
        return _json_list(shots_per_grinder(session, shot_filter))


@reports_bp.get("/grind-regression")
def report_grind_regression() -> ResponseReturnValue:
    """Bivariate linear regression of grind setting vs days-since-roast and grinder temp.

    Returns:
        JSON with per-grinder regression coefficients, R², and data points.
    """
    coffee_id = require_query_int("coffee_id")
    explicit_grinder_id = query_int("grinder_id")
    config = get_config()
    with get_session() as session:
        result = grind_regression(
            session,
            coffee_id,
            explicit_grinder_id,
            params=config.grind_model,
            grinders=config.grinders,
        )
        return jsonify(result.model_dump(mode="json"))


@reports_bp.get("/target-shot-time")
def report_target_shot_time() -> ResponseReturnValue:
    """Weighted moving average target shot time for a coffee/grinder/device combo.

    Query params:
        coffee_id (required): Filter to shots for this coffee bag.
        grinder_id (optional): Further filter by grinder.
        device_id (optional): Further filter by brewing device.

    Returns:
        JSON with target_shot_time (seconds, 1 decimal), n_shots, and filter echo.
    """
    coffee_id = require_query_int("coffee_id")
    grinder_id = query_int("grinder_id")
    device_id = query_int("device_id")
    with get_session() as session:
        wma, n_shots = target_shot_time_wma(
            session, coffee_id, grinder_id, device_id, get_config().grind_model
        )
    response = TargetShotTimeResponse(
        coffee_id=coffee_id,
        grinder_id=grinder_id,
        device_id=device_id,
        target_shot_time=wma,
        n_shots=n_shots,
    )
    return jsonify(response.model_dump(mode="json"))


@reports_bp.post("/grind-model/train")
def report_grind_model_train() -> ResponseReturnValue:
    """Fit (or re-fit) the multivariate grind model for a grinder.

    Each training is a fresh closed-form fit over all current eligible shots;
    previous trainings are kept for history.

    Query params:
        grinder_id (required): Grinder to train for.

    Returns:
        JSON GrindModelTrainingResponse with 201 status.
    """
    grinder_id = require_query_int("grinder_id")
    with get_session() as session:
        result = fit_grind_model(session, grinder_id, get_config().grind_model)
        return jsonify(result.model_dump(mode="json")), HTTPStatus.CREATED


@reports_bp.get("/grind-model/params")
def report_grind_model_params() -> ResponseReturnValue:
    """Retrieve grind model parameters for a grinder.

    Returns the most recent training by default. Use training_id or as_of
    to retrieve a specific historical snapshot.

    Query params:
        grinder_id (required): Grinder whose model to fetch.
        training_id (optional): Return this specific training run.
        as_of (optional): ISO date — return the most recent training on or
                          before this date.

    Returns:
        JSON GrindModelParamsResponse including data points for plotting.
    """
    grinder_id = require_query_int("grinder_id")
    training_id = query_int("training_id")
    as_of = query_date("as_of")
    config = get_config()
    with get_session() as session:
        result = get_grind_model_params(
            session,
            grinder_id,
            training_id,
            as_of,
            params=config.grind_model,
            grinders=config.grinders,
        )
        return jsonify(result.model_dump(mode="json"))


@reports_bp.get("/by-coffee/<int:coffee_id>")
def report_by_coffee(coffee_id: int) -> ResponseReturnValue:
    """All stats scoped to one coffee bag.

    Args:
        coffee_id: Coffee primary key.

    Returns:
        JSON dict with aggregate stats and shot list.
    """
    shot_filter = ShotFilter(
        date_from=query_date("date_from"),
        date_to=query_date("date_to"),
        coffee_id=coffee_id,
    ).with_default_range(get_config().reports.default_range_days)
    with get_session() as session:
        return jsonify(by_coffee(session, shot_filter).model_dump(mode="json"))
