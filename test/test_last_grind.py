"""Tests for GET /api/shots/last-grind (New Shot grind-setting default)."""

from flask.testing import FlaskClient


def _create(client: FlaskClient, url: str, body: dict[str, object]) -> int:
    resp = client.post(url, json=body)
    assert resp.status_code == 201, resp.get_json()
    return int(resp.get_json()["id"])


def _coffee(client: FlaskClient, name: str = "Alpha") -> int:
    return _create(client, "/api/coffees", {"name": name, "roaster": "R"})


def _grinder(client: FlaskClient, make: str, model: str) -> int:
    return _create(
        client, "/api/grinders", {"make": make, "model": model, "type": "flat"}
    )


def _shot(client: FlaskClient, **fields: object) -> int:
    body: dict[str, object] = {"date": "2026-03-01", "maker": "Scott"} | fields
    return _create(client, "/api/shots", body)


def _last_grind(client: FlaskClient, query: str) -> dict[str, object]:
    resp = client.get(f"/api/shots/last-grind?{query}")
    assert resp.status_code == 200, resp.get_json()
    data: dict[str, object] = resp.get_json()
    return data


def test_first_shot_of_coffee_has_no_default(client: FlaskClient) -> None:
    """A coffee with no shots yields a null grind (form stays empty)."""
    coffee_id = _coffee(client)
    assert _last_grind(client, f"coffee_id={coffee_id}") == {
        "coffee_id": coffee_id,
        "grinder_id": None,
        "grind_setting": None,
        "shot_id": None,
        "date": None,
    }


def test_returns_most_recent_grind_for_coffee(client: FlaskClient) -> None:
    """The newest shot by date wins, regardless of entry order."""
    coffee_id = _coffee(client)
    other_coffee = _coffee(client, "Bravo")
    _shot(client, coffee_id=coffee_id, date="2026-03-05", grind_setting="19.5")
    newest = _shot(client, coffee_id=coffee_id, date="2026-03-09", grind_setting="18")
    _shot(
        client, coffee_id=coffee_id, date="2026-03-07", grind_setting="21"
    )  # back-dated
    _shot(client, coffee_id=other_coffee, date="2026-03-10", grind_setting="25")

    data = _last_grind(client, f"coffee_id={coffee_id}")
    assert data["grind_setting"] == "18"
    assert data["shot_id"] == newest
    assert data["date"] == "2026-03-09"


def test_same_day_uses_last_entered_shot(client: FlaskClient) -> None:
    """Several shots on one day resolve to the one entered last."""
    coffee_id = _coffee(client)
    _shot(client, coffee_id=coffee_id, grind_setting="19")
    last = _shot(client, coffee_id=coffee_id, grind_setting="19.5")
    assert _last_grind(client, f"coffee_id={coffee_id}")["shot_id"] == last


def test_skips_shots_without_a_grind(client: FlaskClient) -> None:
    """Shots with no (or blank) grind setting don't erase the last known value."""
    coffee_id = _coffee(client)
    _shot(client, coffee_id=coffee_id, date="2026-03-01", grind_setting="19.5")
    _shot(client, coffee_id=coffee_id, date="2026-03-02")
    _shot(client, coffee_id=coffee_id, date="2026-03-03", grind_setting="")
    assert _last_grind(client, f"coffee_id={coffee_id}")["grind_setting"] == "19.5"


def test_grinder_filter_keeps_notation_consistent(client: FlaskClient) -> None:
    """With grinder_id, only that grinder's settings are considered."""
    coffee_id = _coffee(client)
    mazzer = _grinder(client, "Mazzer", "Mini")
    option_o = _grinder(client, "Option-O", "Lagom P64")
    _shot(
        client,
        coffee_id=coffee_id,
        grinder_id=option_o,
        date="2026-03-01",
        grind_setting="19.5",
    )
    _shot(
        client,
        coffee_id=coffee_id,
        grinder_id=mazzer,
        date="2026-03-02",
        grind_setting="8+5 1/2",
    )

    assert _last_grind(client, f"coffee_id={coffee_id}")["grind_setting"] == "8+5 1/2"
    scoped = _last_grind(client, f"coffee_id={coffee_id}&grinder_id={option_o}")
    assert scoped["grind_setting"] == "19.5"
    assert scoped["grinder_id"] == option_o
    unused = _grinder(client, "Baratza", "Virtuoso+")
    assert (
        _last_grind(client, f"coffee_id={coffee_id}&grinder_id={unused}")[
            "grind_setting"
        ]
        is None
    )


def test_parameter_validation(client: FlaskClient) -> None:
    """coffee_id is required and ids must be integers."""
    resp = client.get("/api/shots/last-grind")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "coffee_id required"}
    assert client.get("/api/shots/last-grind?coffee_id=x").status_code == 400
    assert (
        client.get("/api/shots/last-grind?coffee_id=1&grinder_id=y").status_code == 400
    )
