"""Tests for the equipment blueprint."""

from flask.testing import FlaskClient


def _create_grinder(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    data = {"make": "Baratza", "model": "Vario", "type": "flat", **kwargs}
    resp = client.post("/api/grinders", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def _create_device(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    data = {"make": "Breville", "model": "Barista Express", "type": "espresso", **kwargs}
    resp = client.post("/api/brewing-devices", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def _create_scale(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    data = {"make": "Acaia", "model": "Pearl", **kwargs}
    resp = client.post("/api/scales", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


# ── Grinders ──────────────────────────────────────────────────────────────────


def test_grinder_crud(client: FlaskClient) -> None:
    """Full CRUD cycle for grinders."""
    # Create
    g = _create_grinder(client)
    assert g["make"] == "Baratza"
    assert g["type"] == "flat"

    # Read
    resp = client.get(f"/api/grinders/{g['id']}")
    assert resp.status_code == 200

    # Update
    resp = client.put(f"/api/grinders/{g['id']}", json={"model": "Sette 270"})
    assert resp.status_code == 200
    assert resp.get_json()["model"] == "Sette 270"

    # Delete
    assert client.delete(f"/api/grinders/{g['id']}").status_code == 204
    assert client.get(f"/api/grinders/{g['id']}").status_code == 404


def test_grinder_invalid_type(client: FlaskClient) -> None:
    """Invalid grinder type returns 422."""
    resp = client.post(
        "/api/grinders",
        json={"make": "X", "model": "Y", "type": "laser"},
    )
    assert resp.status_code == 422


def test_grinder_delete_with_shots_returns_409(client: FlaskClient) -> None:
    """Grinder with shots cannot be deleted."""
    g = _create_grinder(client)
    client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Sara", "grinder_id": g["id"]},
    )
    assert client.delete(f"/api/grinders/{g['id']}").status_code == 409


def test_grinder_not_found(client: FlaskClient) -> None:
    """GET/PUT/DELETE on missing grinder returns 404."""
    assert client.get("/api/grinders/9999").status_code == 404
    assert client.put("/api/grinders/9999", json={"make": "X"}).status_code == 404
    assert client.delete("/api/grinders/9999").status_code == 404


# ── Brewing Devices ───────────────────────────────────────────────────────────


def test_brewing_device_crud(client: FlaskClient) -> None:
    """Full CRUD cycle for brewing devices."""
    d = _create_device(client, warmup_minutes=15.0)
    assert d["warmup_minutes"] == 15.0

    resp = client.put(f"/api/brewing-devices/{d['id']}", json={"model": "Oracle"})
    assert resp.status_code == 200
    assert resp.get_json()["model"] == "Oracle"

    assert client.delete(f"/api/brewing-devices/{d['id']}").status_code == 204


def test_device_delete_with_shots_returns_409(client: FlaskClient) -> None:
    """Device with shots cannot be deleted."""
    d = _create_device(client)
    client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "device_id": d["id"]},
    )
    assert client.delete(f"/api/brewing-devices/{d['id']}").status_code == 409


# ── Scales ────────────────────────────────────────────────────────────────────


def test_scale_crud(client: FlaskClient) -> None:
    """Full CRUD cycle for scales."""
    s = _create_scale(client, notes="Very accurate")
    assert s["notes"] == "Very accurate"

    resp = client.put(f"/api/scales/{s['id']}", json={"model": "Lunar"})
    assert resp.status_code == 200
    assert resp.get_json()["model"] == "Lunar"

    assert client.delete(f"/api/scales/{s['id']}").status_code == 204


def test_scale_delete_with_shots_returns_409(client: FlaskClient) -> None:
    """Scale with shots cannot be deleted."""
    s = _create_scale(client)
    client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Sara", "scale_id": s["id"]},
    )
    assert client.delete(f"/api/scales/{s['id']}").status_code == 409
