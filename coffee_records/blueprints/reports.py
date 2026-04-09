"""Reports blueprint — /api/reports/*."""

from datetime import date

from flask import Blueprint, jsonify, request

from coffee_records.database import get_session
from coffee_records.services.reports import (
    by_coffee,
    dose_yield_over_time,
    extraction_trends,
    fit_grind_model,
    get_grind_model_params,
    grind_regression,
    shots_per_day,
    target_shot_time_wma,
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


def _parse_filters() -> tuple[int | None, int | None, int | None]:
    """Parse coffee_id, grinder_id, device_id query parameters.

    Returns:
        Tuple of (coffee_id, grinder_id, device_id), any may be None.
    """
    coffee_id = int(c) if (c := request.args.get("coffee_id")) else None
    grinder_id = int(g) if (g := request.args.get("grinder_id")) else None
    device_id = int(d) if (d := request.args.get("device_id")) else None
    return coffee_id, grinder_id, device_id


@reports_bp.get("/dose-yield")
def report_dose_yield() -> object:
    """Dose vs yield ratio over time.

    Returns:
        JSON list of dose/yield data points.
    """
    date_from, date_to = _parse_dates()
    coffee_id, grinder_id, device_id = _parse_filters()
    with get_session() as session:
        return jsonify(
            dose_yield_over_time(
                session, date_from, date_to, coffee_id, grinder_id, device_id
            )
        )


@reports_bp.get("/shots-per-day")
def report_shots_per_day() -> object:
    """Shot count grouped by date.

    Returns:
        JSON list of date/count pairs.
    """
    date_from, date_to = _parse_dates()
    coffee_id, grinder_id, device_id = _parse_filters()
    with get_session() as session:
        return jsonify(
            shots_per_day(
                session, date_from, date_to, coffee_id, grinder_id, device_id
            )
        )


@reports_bp.get("/extraction-trends")
def report_extraction_trends() -> object:
    """Extraction time over time.

    Returns:
        JSON list of extraction time data points.
    """
    date_from, date_to = _parse_dates()
    coffee_id, grinder_id, device_id = _parse_filters()
    with get_session() as session:
        return jsonify(
            extraction_trends(
                session, date_from, date_to, coffee_id, grinder_id, device_id
            )
        )


@reports_bp.get("/grind-regression")
def report_grind_regression() -> object:
    """Bivariate linear regression of grind setting vs days-since-roast and grinder temp.

    Returns:
        JSON with per-grinder regression coefficients, R², and data points.
    """
    raw = request.args.get("coffee_id")
    if not raw:
        return jsonify({"error": "coffee_id required"}), 400
    try:
        coffee_id = int(raw)
    except ValueError:
        return jsonify({"error": "coffee_id must be an integer"}), 400
    explicit_grinder_id = int(g) if (g := request.args.get("grinder_id")) else None

    with get_session() as session:
        try:
            return jsonify(grind_regression(session, coffee_id, explicit_grinder_id))
        except ValueError as exc:
            msg = str(exc)
            if msg == "not_found":
                return jsonify({"error": "coffee not found"}), 404
            if msg == "no_roast_date":
                return jsonify({"error": "coffee has no roast_date"}), 404
            if msg == "insufficient_data":
                return jsonify({"error": "fewer than 3 usable data points"}), 422
            raise


@reports_bp.get("/target-shot-time")
def report_target_shot_time() -> object:
    """Weighted moving average target shot time for a coffee/grinder/device combo.

    Query params:
        coffee_id (required): Filter to shots for this coffee bag.
        grinder_id (optional): Further filter by grinder.
        device_id (optional): Further filter by brewing device.

    Returns:
        JSON with target_shot_time (seconds, 1 decimal), n_shots, and filter echo.
    """
    raw = request.args.get("coffee_id")
    if not raw:
        return jsonify({"error": "coffee_id required"}), 400
    try:
        coffee_id = int(raw)
    except ValueError:
        return jsonify({"error": "coffee_id must be an integer"}), 400

    grinder_id = int(g) if (g := request.args.get("grinder_id")) else None
    device_id = int(d) if (d := request.args.get("device_id")) else None

    with get_session() as session:
        wma, n_shots = target_shot_time_wma(session, coffee_id, grinder_id, device_id)
        return jsonify(
            {
                "coffee_id": coffee_id,
                "grinder_id": grinder_id,
                "device_id": device_id,
                "target_shot_time": wma,
                "n_shots": n_shots,
            }
        )


@reports_bp.post("/grind-model/train")
def report_grind_model_train() -> object:
    """Fit (or re-fit) the multivariate grind model for a grinder.

    Warm-starts from the most recent existing training for this grinder.
    New coffees are initialized to a mid-range Mazzer setting (85.0).

    Query params:
        grinder_id (required): Grinder to train for.

    Returns:
        JSON GrindModelTrainingResponse with 201 status.
    """
    raw = request.args.get("grinder_id")
    if not raw:
        return jsonify({"error": "grinder_id required"}), 400
    try:
        grinder_id = int(raw)
    except ValueError:
        return jsonify({"error": "grinder_id must be an integer"}), 400

    with get_session() as session:
        try:
            result = fit_grind_model(session, grinder_id)
            return jsonify(result), 201
        except ValueError as exc:
            msg = str(exc)
            if msg == "grinder_not_found":
                return jsonify({"error": "grinder not found"}), 404
            if msg == "insufficient_data":
                return jsonify({"error": "fewer than 3 usable shots after filtering"}), 422
            raise


@reports_bp.get("/grind-model/params")
def report_grind_model_params() -> object:
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
    raw = request.args.get("grinder_id")
    if not raw:
        return jsonify({"error": "grinder_id required"}), 400
    try:
        grinder_id = int(raw)
    except ValueError:
        return jsonify({"error": "grinder_id must be an integer"}), 400

    training_id = int(t) if (t := request.args.get("training_id")) else None

    as_of = None
    if ao := request.args.get("as_of"):
        try:
            from datetime import date as _date
            as_of = _date.fromisoformat(ao)
        except ValueError:
            return jsonify({"error": "as_of must be an ISO date (YYYY-MM-DD)"}), 400

    with get_session() as session:
        try:
            result = get_grind_model_params(session, grinder_id, training_id, as_of)
            return jsonify(result)
        except ValueError as exc:
            msg = str(exc)
            if msg == "grinder_not_found":
                return jsonify({"error": "grinder not found"}), 404
            if msg == "no_training":
                return jsonify({"error": "no trained model found for this grinder"}), 404
            raise


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
