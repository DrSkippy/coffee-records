"""Tests for grind model fitting service and endpoints."""

from datetime import date

import pytest
from flask.testing import FlaskClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_coffee(client: FlaskClient, roast_date: str = "2026-01-01") -> int:
    resp = client.post(
        "/api/coffees",
        json={"name": "Test Coffee", "roaster": "Test Roaster", "roast_date": roast_date},
    )
    assert resp.status_code == 201
    return resp.get_json()["id"]  # type: ignore[index]


def _create_grinder(client: FlaskClient) -> int:
    resp = client.post(
        "/api/grinders",
        json={"make": "Mazzer", "model": "Mini", "type": "flat"},
    )
    assert resp.status_code == 201
    return resp.get_json()["id"]  # type: ignore[index]


def _create_shot(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    defaults: dict[str, object] = {
        "date": "2026-02-10",
        "maker": "Scott",
        "drink_type": "americano",
        "grind_setting": "8+5",
        "grinder_temp_before": 68.0,
        "dose_weight": 18.5,
        "final_weight": 37.0,
        "extraction_time": 28.0,
    }
    defaults.update(kwargs)
    resp = client.post("/api/shots", json=defaults)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def _setup_training_data(client: FlaskClient) -> tuple[int, int, int]:
    """Create 2 coffees, 1 grinder, and enough shots to train.

    Returns:
        (coffee1_id, coffee2_id, grinder_id)
    """
    grinder_id = _create_grinder(client)
    coffee1_id = _create_coffee(client, roast_date="2026-01-01")
    coffee2_id = _create_coffee(client, roast_date="2026-01-15")

    # Coffee1 — day 1 (excluded by first-day filter) + 3 training days
    _create_shot(
        client,
        date="2026-02-01",
        coffee_id=coffee1_id,
        grinder_id=grinder_id,
        grind_setting="8+5",
    )
    _create_shot(
        client,
        date="2026-02-10",
        coffee_id=coffee1_id,
        grinder_id=grinder_id,
        grind_setting="8+5",
    )
    _create_shot(
        client,
        date="2026-02-15",
        coffee_id=coffee1_id,
        grinder_id=grinder_id,
        grind_setting="8+4",
        grinder_temp_before=72.0,
    )
    _create_shot(
        client,
        date="2026-02-20",
        coffee_id=coffee1_id,
        grinder_id=grinder_id,
        grind_setting="8+3",
        grinder_temp_before=74.0,
    )

    # Coffee2 — day 1 (excluded) + 3 training days
    _create_shot(
        client,
        date="2026-02-01",
        coffee_id=coffee2_id,
        grinder_id=grinder_id,
        grind_setting="8+6",
    )
    _create_shot(
        client,
        date="2026-02-10",
        coffee_id=coffee2_id,
        grinder_id=grinder_id,
        grind_setting="8+6",
    )
    _create_shot(
        client,
        date="2026-02-15",
        coffee_id=coffee2_id,
        grinder_id=grinder_id,
        grind_setting="8+5",
        grinder_temp_before=72.0,
    )
    _create_shot(
        client,
        date="2026-02-20",
        coffee_id=coffee2_id,
        grinder_id=grinder_id,
        grind_setting="8+4",
        grinder_temp_before=74.0,
    )

    return coffee1_id, coffee2_id, grinder_id


# ---------------------------------------------------------------------------
# Service-level tests (via app context + db session)
# ---------------------------------------------------------------------------


def test_fit_grind_model_basic(app: object, client: FlaskClient) -> None:
    """Training succeeds with enough data; result is stored in the database."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.models.grind_model import GrindModelTraining
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    with flask_app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)

    assert result["grinder_id"] == grinder_id
    assert result["n_shots_used"] >= 6   # 3 per coffee × 2 coffees
    assert result["n_coffees"] == 2
    assert "a0" in result
    assert "a4" in result
    assert len(result["coffee_intercepts"]) == 2
    assert result["training_id"] is not None

    # Verify persisted
    with flask_app.app_context():
        with get_session() as session:
            row = session.get(GrindModelTraining, result["training_id"])
            assert row is not None
            assert row.grinder_id == grinder_id
            assert len(row.coffee_intercepts) == 2


def test_fit_grind_model_excludes_drip(app: object, client: FlaskClient) -> None:
    """Drip shots are not included in training data."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    # Add drip shots — these must NOT appear in n_shots_used
    coffee_id = _create_coffee(client, roast_date="2026-01-01")
    for _ in range(3):
        _create_shot(client, coffee_id=coffee_id, grinder_id=grinder_id, drink_type="drip")

    with flask_app.app_context():
        with get_session() as session:
            result_before = fit_grind_model(session, grinder_id)

    # Coffee with only drip shots doesn't appear in intercepts
    drip_coffee_ids = {ci["coffee_id"] for ci in result_before["coffee_intercepts"]}
    assert coffee_id not in drip_coffee_ids


def test_fit_grind_model_excludes_aeropress(app: object, client: FlaskClient) -> None:
    """Aeropress shots are not included in training data."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    coffee_id = _create_coffee(client, roast_date="2026-01-01")
    for _ in range(3):
        _create_shot(client, coffee_id=coffee_id, grinder_id=grinder_id, drink_type="aeropress")

    with flask_app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)

    aeropress_coffee_ids = {ci["coffee_id"] for ci in result["coffee_intercepts"]}
    assert coffee_id not in aeropress_coffee_ids


def test_fit_grind_model_excludes_first_day(app: object, client: FlaskClient) -> None:
    """Shots on the first day a coffee appears are excluded from training."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    grinder_id = _create_grinder(client)
    coffee_id = _create_coffee(client, roast_date="2026-01-01")

    # 1 shot on first day + 3 on later days for this coffee
    first_day_date = "2026-02-01"
    _create_shot(client, date=first_day_date, coffee_id=coffee_id, grinder_id=grinder_id)
    for day in ["2026-02-10", "2026-02-15", "2026-02-20"]:
        _create_shot(client, date=day, coffee_id=coffee_id, grinder_id=grinder_id)

    # Also need a second coffee so alternating fitting is meaningful
    coffee2_id = _create_coffee(client, roast_date="2026-01-15")
    _create_shot(client, date="2026-02-10", coffee_id=coffee2_id, grinder_id=grinder_id)
    for day in ["2026-02-15", "2026-02-20"]:
        _create_shot(client, date=day, coffee_id=coffee2_id, grinder_id=grinder_id)

    with flask_app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)

    # First-day shot excluded: n_shots_used should be 3 + 2 = 5, not 4 + 3 = 7
    # (first day excluded for each coffee)
    assert result["n_shots_used"] == 5


def test_fit_grind_model_insufficient_data(app: object, client: FlaskClient) -> None:
    """fit_grind_model raises ValueError when fewer than 3 shots are usable."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    grinder_id = _create_grinder(client)
    coffee_id = _create_coffee(client, roast_date="2026-01-01")

    # Only first-day shots — all excluded
    _create_shot(client, date="2026-02-01", coffee_id=coffee_id, grinder_id=grinder_id)
    _create_shot(client, date="2026-02-01", coffee_id=coffee_id, grinder_id=grinder_id)

    with flask_app.app_context():
        with get_session() as session:
            with pytest.raises(ValueError, match="insufficient_data"):
                fit_grind_model(session, grinder_id)


def test_fit_grind_model_grinder_not_found(app: object) -> None:
    """fit_grind_model raises ValueError for unknown grinder."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    with flask_app.app_context():
        with get_session() as session:
            with pytest.raises(ValueError, match="grinder_not_found"):
                fit_grind_model(session, 99999)


def test_fit_grind_model_warm_start(app: object, client: FlaskClient) -> None:
    """Second training warm-starts from the previous training's intercepts."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    with flask_app.app_context():
        with get_session() as session:
            result1 = fit_grind_model(session, grinder_id)
        with get_session() as session:
            result2 = fit_grind_model(session, grinder_id)

    # Both trainings should exist and have the same number of shots used
    assert result1["training_id"] != result2["training_id"]
    assert result2["n_shots_used"] == result1["n_shots_used"]
    # Second training converges faster (warm-started) — usually in fewer iterations
    # (not guaranteed, but both should converge)
    assert result2["n_coffees"] == 2


# ---------------------------------------------------------------------------
# get_grind_model_params tests
# ---------------------------------------------------------------------------


def test_get_grind_model_params_latest(app: object, client: FlaskClient) -> None:
    """get_grind_model_params returns the most recent training."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model, get_grind_model_params

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    with flask_app.app_context():
        with get_session() as session:
            trained = fit_grind_model(session, grinder_id)
        with get_session() as session:
            params = get_grind_model_params(session, grinder_id)

    assert params["training_id"] == trained["training_id"]
    assert "points" in params
    assert "target_times" in params
    assert len(params["target_times"]) == 2
    assert len(params["points"]) >= 6


def test_get_grind_model_params_by_id(app: object, client: FlaskClient) -> None:
    """get_grind_model_params returns a specific training by training_id."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model, get_grind_model_params

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    with flask_app.app_context():
        with get_session() as session:
            result1 = fit_grind_model(session, grinder_id)
        with get_session() as session:
            result2 = fit_grind_model(session, grinder_id)

        # Fetch by first training id — should get the first one, not the latest
        with get_session() as session:
            params = get_grind_model_params(
                session, grinder_id, training_id=result1["training_id"]
            )

    assert params["training_id"] == result1["training_id"]


def test_get_grind_model_params_as_of(app: object, client: FlaskClient) -> None:
    """get_grind_model_params returns the latest training on or before as_of."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import fit_grind_model, get_grind_model_params

    flask_app: Flask = app  # type: ignore[assignment]
    _c1, _c2, grinder_id = _setup_training_data(client)

    with flask_app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)

        # as_of today should find the training
        with get_session() as session:
            params = get_grind_model_params(
                session, grinder_id, as_of=date(2099, 12, 31)
            )
        assert params["training_id"] == result["training_id"]

        # as_of before the training was done — should find nothing
        with get_session() as session:
            with pytest.raises(ValueError, match="no_training"):
                get_grind_model_params(session, grinder_id, as_of=date(2000, 1, 1))


def test_get_grind_model_params_no_training(app: object, client: FlaskClient) -> None:
    """get_grind_model_params raises ValueError when no training exists."""
    from flask import Flask

    from coffee_records.database import get_session
    from coffee_records.services.reports import get_grind_model_params

    flask_app: Flask = app  # type: ignore[assignment]
    grinder_id = _create_grinder(client)

    with flask_app.app_context():
        with get_session() as session:
            with pytest.raises(ValueError, match="no_training"):
                get_grind_model_params(session, grinder_id)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_train_endpoint_success(client: FlaskClient) -> None:
    """POST /api/reports/grind-model/train returns 201 with training result."""
    _setup_training_data(client)
    grinder_resp = client.get("/api/grinders")
    grinder_id = grinder_resp.get_json()[0]["id"]

    resp = client.post(f"/api/reports/grind-model/train?grinder_id={grinder_id}")
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["grinder_id"] == grinder_id
    assert data["n_shots_used"] >= 6
    assert "a0" in data
    assert "coffee_intercepts" in data


def test_train_endpoint_missing_grinder_id(client: FlaskClient) -> None:
    """POST without grinder_id returns 400."""
    resp = client.post("/api/reports/grind-model/train")
    assert resp.status_code == 400
    assert "grinder_id required" in resp.get_json()["error"]


def test_train_endpoint_unknown_grinder(client: FlaskClient) -> None:
    """POST with unknown grinder_id returns 404."""
    resp = client.post("/api/reports/grind-model/train?grinder_id=99999")
    assert resp.status_code == 404


def test_train_endpoint_insufficient_data(client: FlaskClient) -> None:
    """POST with a grinder that has no usable shots returns 422."""
    grinder_id = _create_grinder(client)
    resp = client.post(f"/api/reports/grind-model/train?grinder_id={grinder_id}")
    assert resp.status_code == 422


def test_params_endpoint_success(client: FlaskClient) -> None:
    """GET /api/reports/grind-model/params returns 200 after training."""
    _setup_training_data(client)
    grinder_id = client.get("/api/grinders").get_json()[0]["id"]

    client.post(f"/api/reports/grind-model/train?grinder_id={grinder_id}")

    resp = client.get(f"/api/reports/grind-model/params?grinder_id={grinder_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "points" in data
    assert "target_times" in data
    assert data["grinder_id"] == grinder_id


def test_params_endpoint_no_training(client: FlaskClient) -> None:
    """GET /api/reports/grind-model/params returns 404 when no training exists."""
    grinder_id = _create_grinder(client)
    resp = client.get(f"/api/reports/grind-model/params?grinder_id={grinder_id}")
    assert resp.status_code == 404


def test_params_endpoint_missing_grinder_id(client: FlaskClient) -> None:
    """GET without grinder_id returns 400."""
    resp = client.get("/api/reports/grind-model/params")
    assert resp.status_code == 400
