"""Tests for the reports blueprint."""

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
