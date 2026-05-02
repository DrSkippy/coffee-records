"""Tests for the defaults blueprint."""

from flask.testing import FlaskClient

_FULL_PAYLOAD = {
    "maker": "Sara",
    "dose_weight": 18.0,
    "pre_infusion_time": "4+4",
    "extraction_time": 30.0,
    "final_weight": 36.0,
    "drink_type": "latte",
    "grinder_temp_before": 62.0,
    "wedge": False,
    "shaker": True,
    "wdt": False,
    "flow_taper": True,
}


def test_get_defaults_creates_row_if_absent(client: FlaskClient) -> None:
    """GET on an empty DB returns 200 and seeds the row with hardcoded fallbacks."""
    resp = client.get("/api/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["maker"] == "Scott"
    assert data["dose_weight"] == 20.0
    assert data["pre_infusion_time"] == "5+5"
    assert data["extraction_time"] == 28.0
    assert data["final_weight"] == 40.0
    assert data["drink_type"] == "americano"
    assert data["grinder_temp_before"] == 64.0
    assert data["wedge"] is True
    assert data["shaker"] is True
    assert data["wdt"] is True
    assert data["flow_taper"] is False


def test_get_defaults_returns_existing_row(client: FlaskClient) -> None:
    """GET after PUT returns the stored values, not the seed values."""
    client.put("/api/defaults", json=_FULL_PAYLOAD)
    resp = client.get("/api/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["maker"] == "Sara"
    assert data["drink_type"] == "latte"
    assert data["wedge"] is False


def test_put_defaults_updates(client: FlaskClient) -> None:
    """PUT with changed values persists and returns the new values."""
    resp = client.put("/api/defaults", json=_FULL_PAYLOAD)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["maker"] == "Sara"
    assert data["dose_weight"] == 18.0
    assert data["flow_taper"] is True


def test_put_defaults_clears_nullable_field(client: FlaskClient) -> None:
    """PUT with null for a nullable field stores NULL."""
    payload = {**_FULL_PAYLOAD, "dose_weight": None, "drink_type": None}
    resp = client.put("/api/defaults", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dose_weight"] is None
    assert data["drink_type"] is None


def test_get_after_put_roundtrip(client: FlaskClient) -> None:
    """Values written via PUT are returned unchanged by GET."""
    client.put("/api/defaults", json=_FULL_PAYLOAD)
    data = client.get("/api/defaults").get_json()
    for key, value in _FULL_PAYLOAD.items():
        assert data[key] == value, f"Mismatch on {key}"


def test_put_defaults_missing_maker_returns_422(client: FlaskClient) -> None:
    """PUT without the required maker field returns 422."""
    payload = {k: v for k, v in _FULL_PAYLOAD.items() if k != "maker"}
    resp = client.put("/api/defaults", json=payload)
    assert resp.status_code == 422
