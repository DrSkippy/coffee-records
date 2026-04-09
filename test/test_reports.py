"""Tests for the reports blueprint."""

import os

from flask.testing import FlaskClient


def _create_shot(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    data = {"date": "2026-03-20", "maker": "Scott", **kwargs}
    resp = client.post("/api/shots", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def _create_coffee(client: FlaskClient) -> int:
    resp = client.post("/api/coffees", json={"name": "Blend", "roaster": "Roaster"})
    return resp.get_json()["id"]  # type: ignore[index]


def test_dose_yield_empty(client: FlaskClient) -> None:
    """Dose-yield report returns empty list with no shots."""
    resp = client.get("/api/reports/dose-yield?date_from=2026-01-01&date_to=2026-12-31")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_dose_yield_ratio_calculation(client: FlaskClient) -> None:
    """Dose-yield report calculates ratio correctly."""
    _create_shot(client, dose_weight=18.0, final_weight=36.0)
    resp = client.get("/api/reports/dose-yield?date_from=2026-01-01&date_to=2026-12-31")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["ratio"] == 2.0
    assert data[0]["dose_weight"] == 18.0
    assert data[0]["final_weight"] == 36.0


def test_dose_yield_excludes_null_weights(client: FlaskClient) -> None:
    """Shots without dose/final weight are excluded from dose-yield report."""
    _create_shot(client)  # no weights
    _create_shot(client, dose_weight=18.0, final_weight=36.0)
    resp = client.get("/api/reports/dose-yield?date_from=2026-01-01&date_to=2026-12-31")
    assert len(resp.get_json()) == 1


def test_shots_per_day(client: FlaskClient) -> None:
    """Shots-per-day report groups correctly."""
    _create_shot(client, date="2026-03-18")
    _create_shot(client, date="2026-03-18")
    _create_shot(client, date="2026-03-19")
    resp = client.get("/api/reports/shots-per-day?date_from=2026-03-01&date_to=2026-03-31")
    data = resp.get_json()
    counts = {row["date"]: row["count"] for row in data}
    assert counts["2026-03-18"] == 2
    assert counts["2026-03-19"] == 1


def test_extraction_trends(client: FlaskClient) -> None:
    """Extraction-trends report returns extraction times."""
    _create_shot(client, extraction_time=28.5)
    _create_shot(client)  # no extraction_time
    resp = client.get("/api/reports/extraction-trends?date_from=2026-01-01&date_to=2026-12-31")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["extraction_time"] == 28.5


def test_by_coffee_stats(client: FlaskClient) -> None:
    """By-coffee report computes aggregate stats correctly."""
    coffee_id = _create_coffee(client)
    _create_shot(client, coffee_id=coffee_id, dose_weight=18.0, final_weight=36.0, extraction_time=28.0)
    _create_shot(client, coffee_id=coffee_id, dose_weight=19.0, final_weight=38.0, extraction_time=30.0)
    _create_shot(client)  # different coffee, should not appear

    resp = client.get(
        f"/api/reports/by-coffee/{coffee_id}?date_from=2026-01-01&date_to=2026-12-31"
    )
    data = resp.get_json()
    assert data["total_shots"] == 2
    assert data["avg_dose"] == 18.5
    assert data["avg_final_weight"] == 37.0
    assert data["avg_extraction_time"] == 29.0
    assert data["avg_ratio"] == 2.0
    assert len(data["shots"]) == 2


def test_by_coffee_no_shots(client: FlaskClient) -> None:
    """By-coffee report returns zeros for coffee with no shots."""
    coffee_id = _create_coffee(client)
    resp = client.get(
        f"/api/reports/by-coffee/{coffee_id}?date_from=2026-01-01&date_to=2026-12-31"
    )
    data = resp.get_json()
    assert data["total_shots"] == 0
    assert data["avg_dose"] is None


# ---------------------------------------------------------------------------
# target-shot-time endpoint
# ---------------------------------------------------------------------------


def _create_grinder(client: FlaskClient) -> int:
    resp = client.post(
        "/api/grinders", json={"make": "Acme", "model": "G1", "type": "flat"}
    )
    assert resp.status_code == 201
    return resp.get_json()["id"]  # type: ignore[index]


def _create_device(client: FlaskClient) -> int:
    resp = client.post(
        "/api/brewing-devices",
        json={"make": "Acme", "model": "M1", "type": "espresso"},
    )
    assert resp.status_code == 201
    return resp.get_json()["id"]  # type: ignore[index]


def test_target_shot_time_no_coffee_id(client: FlaskClient) -> None:
    """Returns 400 when coffee_id is missing."""
    resp = client.get("/api/reports/target-shot-time")
    assert resp.status_code == 400
    assert "coffee_id required" in resp.get_json()["error"]


def test_target_shot_time_no_shots(client: FlaskClient) -> None:
    """Returns null target_shot_time and n_shots=0 for coffee with no qualifying shots."""
    coffee_id = _create_coffee(client)
    resp = client.get(f"/api/reports/target-shot-time?coffee_id={coffee_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["target_shot_time"] is None
    assert data["n_shots"] == 0


def test_target_shot_time_single_shot(client: FlaskClient) -> None:
    """Single shot — WMA equals the corrected extraction time."""
    coffee_id = _create_coffee(client)
    _create_shot(
        client,
        coffee_id=coffee_id,
        extraction_time=30.0,
        extraction_delta=0.0,
        drink_type="americano",
    )
    resp = client.get(f"/api/reports/target-shot-time?coffee_id={coffee_id}")
    data = resp.get_json()
    assert data["target_shot_time"] == 30.0
    assert data["n_shots"] == 1


def test_target_shot_time_wma_weights_recent(client: FlaskClient) -> None:
    """WMA gives higher weight to recent shots than simple mean would.

    Shots: 25s (older date), 35s (newer date).
    Simple mean = 30.0; WMA = (1*25 + 2*35)/3 = 95/3 ≈ 31.7.
    """
    coffee_id = _create_coffee(client)
    _create_shot(
        client,
        coffee_id=coffee_id,
        date="2026-01-10",
        extraction_time=25.0,
        drink_type="latte",
    )
    _create_shot(
        client,
        coffee_id=coffee_id,
        date="2026-01-20",
        extraction_time=35.0,
        drink_type="latte",
    )
    resp = client.get(f"/api/reports/target-shot-time?coffee_id={coffee_id}")
    data = resp.get_json()
    # WMA = (1*25 + 2*35) / 3 = 31.666... → rounds to 31.7
    assert data["target_shot_time"] == 31.7
    assert data["n_shots"] == 2


def test_target_shot_time_with_delta(client: FlaskClient) -> None:
    """extraction_delta is applied before weighting."""
    coffee_id = _create_coffee(client)
    # t=28, dt=+2 → effective 30
    _create_shot(
        client,
        coffee_id=coffee_id,
        extraction_time=28.0,
        extraction_delta=2.0,
        drink_type="cappuccino",
    )
    resp = client.get(f"/api/reports/target-shot-time?coffee_id={coffee_id}")
    data = resp.get_json()
    assert data["target_shot_time"] == 30.0


def test_target_shot_time_grinder_filter(client: FlaskClient) -> None:
    """grinder_id filter excludes shots from other grinders."""
    coffee_id = _create_coffee(client)
    grinder_a = _create_grinder(client)
    grinder_b = _create_grinder(client)
    # Grinder A: 30s shot
    _create_shot(
        client,
        coffee_id=coffee_id,
        grinder_id=grinder_a,
        extraction_time=30.0,
        drink_type="americano",
    )
    # Grinder B: 40s shot — should be excluded
    _create_shot(
        client,
        coffee_id=coffee_id,
        grinder_id=grinder_b,
        extraction_time=40.0,
        drink_type="americano",
    )
    resp = client.get(
        f"/api/reports/target-shot-time?coffee_id={coffee_id}&grinder_id={grinder_a}"
    )
    data = resp.get_json()
    assert data["target_shot_time"] == 30.0
    assert data["n_shots"] == 1


def test_target_shot_time_device_filter(client: FlaskClient) -> None:
    """device_id filter excludes shots from other brewing devices."""
    coffee_id = _create_coffee(client)
    device_a = _create_device(client)
    device_b = _create_device(client)
    _create_shot(
        client,
        coffee_id=coffee_id,
        device_id=device_a,
        extraction_time=28.0,
        drink_type="latte",
    )
    _create_shot(
        client,
        coffee_id=coffee_id,
        device_id=device_b,
        extraction_time=50.0,
        drink_type="latte",
    )
    resp = client.get(
        f"/api/reports/target-shot-time?coffee_id={coffee_id}&device_id={device_a}"
    )
    data = resp.get_json()
    assert data["target_shot_time"] == 28.0
    assert data["n_shots"] == 1


def test_target_shot_time_excludes_drip(client: FlaskClient) -> None:
    """Drip shots are excluded from the WMA calculation."""
    coffee_id = _create_coffee(client)
    _create_shot(
        client, coffee_id=coffee_id, extraction_time=60.0, drink_type="drip"
    )
    _create_shot(
        client, coffee_id=coffee_id, extraction_time=30.0, drink_type="americano"
    )
    resp = client.get(f"/api/reports/target-shot-time?coffee_id={coffee_id}")
    data = resp.get_json()
    assert data["target_shot_time"] == 30.0
    assert data["n_shots"] == 1


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


def test_api_key_disabled_when_empty(client: FlaskClient) -> None:
    """When api_key is not configured, all /api/* routes are freely accessible."""
    # The test app is created without API_KEY env var, so api_key defaults to "".
    resp = client.get("/api/version")
    assert resp.status_code == 200


def test_api_key_enforced_when_configured(app: object) -> None:
    """When API_KEY env var is set, requests without key get 401."""
    import coffee_records.database as db_module
    from flask import Flask

    from coffee_records import create_app
    from coffee_records.config import Config, AppConfig

    flask_app: Flask = app  # type: ignore[assignment]

    # Save global db state — create_app calls init_db which replaces the global
    # engine/session factory, which would break clean_tables teardown.
    _orig_engine = db_module._engine
    _orig_session = db_module._SessionLocal

    # Temporarily build a second app with api_key configured.
    cfg = Config(app=AppConfig(debug=False, secret_key="test", api_key="secret123"))
    # Bypass env_override by passing Config directly.
    protected_app = create_app(
        config=cfg, database_url=flask_app.config.get("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    )
    protected_app.config["TESTING"] = True
    test_client = protected_app.test_client()

    # No key → 401
    resp = test_client.get("/api/version")
    assert resp.status_code == 401

    # Wrong key → 401
    resp = test_client.get("/api/version", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

    # Correct key → 200
    resp = test_client.get("/api/version", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200

    # Key via query param → 200
    resp = test_client.get("/api/version?api_key=secret123")
    assert resp.status_code == 200

    # Restore original db state so clean_tables teardown works correctly.
    db_module._engine = _orig_engine
    db_module._SessionLocal = _orig_session
