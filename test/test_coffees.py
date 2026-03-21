"""Tests for the coffees blueprint."""

import pytest
from flask.testing import FlaskClient


def _create_coffee(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    """Helper: POST /api/coffees and return JSON response."""
    data = {"name": "Test Blend", "roaster": "Roaster Co", **kwargs}
    resp = client.post("/api/coffees", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def test_list_coffees_empty(client: FlaskClient) -> None:
    """GET /api/coffees returns empty list when no coffees exist."""
    resp = client.get("/api/coffees")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_coffee_minimal(client: FlaskClient) -> None:
    """POST /api/coffees with minimal fields returns 201 with id."""
    data = {"name": "Espresso Blend", "roaster": "Blue Bottle"}
    resp = client.post("/api/coffees", json=data)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["id"] > 0
    assert body["name"] == "Espresso Blend"
    assert body["roaster"] == "Blue Bottle"


def test_create_coffee_full(client: FlaskClient) -> None:
    """POST /api/coffees with all fields stores them correctly."""
    data = {
        "name": "Kenya AA",
        "roaster": "Stumptown",
        "roast_date": "2026-03-01",
        "origin_country": "Kenya",
        "roast_level": "light",
        "variety": "SL28",
        "process": "washed",
    }
    resp = client.post("/api/coffees", json=data)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["roast_level"] == "light"
    assert body["origin_country"] == "Kenya"


def test_create_coffee_invalid_roast_level(client: FlaskClient) -> None:
    """POST /api/coffees with invalid roast_level returns 422."""
    resp = client.post(
        "/api/coffees",
        json={"name": "X", "roaster": "Y", "roast_level": "ultra"},
    )
    assert resp.status_code == 422


def test_get_coffee(client: FlaskClient) -> None:
    """GET /api/coffees/<id> returns the coffee."""
    created = _create_coffee(client)
    resp = client.get(f"/api/coffees/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == created["id"]


def test_get_coffee_not_found(client: FlaskClient) -> None:
    """GET /api/coffees/9999 returns 404."""
    resp = client.get("/api/coffees/9999")
    assert resp.status_code == 404


def test_update_coffee(client: FlaskClient) -> None:
    """PUT /api/coffees/<id> updates the name."""
    created = _create_coffee(client)
    resp = client.put(f"/api/coffees/{created['id']}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Updated Name"


def test_delete_coffee(client: FlaskClient) -> None:
    """DELETE /api/coffees/<id> returns 204."""
    created = _create_coffee(client)
    resp = client.delete(f"/api/coffees/{created['id']}")
    assert resp.status_code == 204
    # Confirm it's gone
    assert client.get(f"/api/coffees/{created['id']}").status_code == 404


def test_delete_coffee_with_shots_returns_409(client: FlaskClient) -> None:
    """DELETE /api/coffees/<id> returns 409 when shots reference it."""
    coffee = _create_coffee(client)
    client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "coffee_id": coffee["id"]},
    )
    resp = client.delete(f"/api/coffees/{coffee['id']}")
    assert resp.status_code == 409


def test_list_coffees_sorted_by_roast_date(client: FlaskClient) -> None:
    """GET /api/coffees returns coffees sorted by roast_date desc."""
    _create_coffee(client, roast_date="2026-01-01")
    _create_coffee(client, roast_date="2026-03-01")
    _create_coffee(client, roast_date="2026-02-01")
    resp = client.get("/api/coffees")
    dates = [c["roast_date"] for c in resp.get_json()]
    assert dates == sorted(dates, reverse=True)
