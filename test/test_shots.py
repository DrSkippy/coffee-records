"""Tests for the shots blueprint."""

from flask.testing import FlaskClient


def _make_coffee(client: FlaskClient) -> int:
    resp = client.post("/api/coffees", json={"name": "Blend", "roaster": "Roaster"})
    return resp.get_json()["id"]  # type: ignore[index]


def _make_grinder(client: FlaskClient) -> int:
    resp = client.post("/api/grinders", json={"make": "Baratza", "model": "Vario", "type": "flat"})
    return resp.get_json()["id"]  # type: ignore[index]


def _make_mazzer(client: FlaskClient) -> int:
    resp = client.post("/api/grinders", json={"make": "Mazzer", "model": "Mini", "type": "flat"})
    return resp.get_json()["id"]  # type: ignore[index]


def _make_option_o(client: FlaskClient) -> int:
    resp = client.post("/api/grinders", json={"make": "Option-O", "model": "Lagom P64", "type": "flat"})
    return resp.get_json()["id"]  # type: ignore[index]


def _make_timemore(client: FlaskClient) -> int:
    resp = client.post("/api/grinders", json={"make": "Timemore", "model": "C3", "type": "conical"})
    return resp.get_json()["id"]  # type: ignore[index]


def _make_device(client: FlaskClient) -> int:
    resp = client.post(
        "/api/brewing-devices",
        json={"make": "Breville", "model": "Barista", "type": "espresso"},
    )
    return resp.get_json()["id"]  # type: ignore[index]


def _make_scale(client: FlaskClient) -> int:
    resp = client.post("/api/scales", json={"make": "Acaia", "model": "Pearl"})
    return resp.get_json()["id"]  # type: ignore[index]


def _create_shot(client: FlaskClient, **kwargs: object) -> dict:  # type: ignore[type-arg]
    data = {"date": "2026-03-20", "maker": "Scott", **kwargs}
    resp = client.post("/api/shots", json=data)
    assert resp.status_code == 201
    return resp.get_json()  # type: ignore[return-value]


def test_create_shot_minimal(client: FlaskClient) -> None:
    """POST /api/shots with just date/maker returns 201."""
    shot = _create_shot(client)
    assert shot["id"] > 0
    assert shot["maker"] == "Scott"
    assert shot["wedge"] is False


def test_create_shot_full(client: FlaskClient) -> None:
    """POST /api/shots with all FK fields populates denorm labels."""
    coffee_id = _make_coffee(client)
    grinder_id = _make_grinder(client)
    device_id = _make_device(client)
    scale_id = _make_scale(client)

    shot = _create_shot(
        client,
        coffee_id=coffee_id,
        grinder_id=grinder_id,
        device_id=device_id,
        scale_id=scale_id,
        dose_weight=18.0,
        final_weight=36.0,
        extraction_time=28.5,
        wedge=True,
        wdt=True,
        drink_type="latte",
    )

    assert shot["coffee_name"] == "Blend"
    assert shot["grinder_label"] == "Baratza Vario"
    assert shot["device_label"] == "Breville Barista"
    assert shot["scale_label"] == "Acaia Pearl"
    assert shot["wedge"] is True
    assert shot["wdt"] is True
    assert shot["drink_type"] == "latte"


def test_denorm_labels_null_when_no_fk(client: FlaskClient) -> None:
    """Denorm labels are None when FK fields are not set."""
    shot = _create_shot(client)
    assert shot["coffee_name"] is None
    assert shot["grinder_label"] is None
    assert shot["device_label"] is None
    assert shot["scale_label"] is None


def test_list_shots_filter_maker(client: FlaskClient) -> None:
    """Filter shots by maker."""
    _create_shot(client, maker="Scott")
    _create_shot(client, maker="Sara")
    resp = client.get("/api/shots?maker=Sara")
    shots = resp.get_json()
    assert all(s["maker"] == "Sara" for s in shots)
    assert len(shots) == 1


def test_list_shots_filter_coffee_id(client: FlaskClient) -> None:
    """Filter shots by coffee_id."""
    coffee_id = _make_coffee(client)
    _create_shot(client, coffee_id=coffee_id)
    _create_shot(client)
    resp = client.get(f"/api/shots?coffee_id={coffee_id}")
    shots = resp.get_json()
    assert len(shots) == 1
    assert shots[0]["coffee_id"] == coffee_id


def test_list_shots_filter_date_range(client: FlaskClient) -> None:
    """Filter shots by date_from and date_to."""
    _create_shot(client, date="2026-01-01")
    _create_shot(client, date="2026-02-15")
    _create_shot(client, date="2026-03-20")
    resp = client.get("/api/shots?date_from=2026-02-01&date_to=2026-02-28")
    shots = resp.get_json()
    assert len(shots) == 1
    assert shots[0]["date"] == "2026-02-15"


def test_list_shots_limit_offset(client: FlaskClient) -> None:
    """Limit and offset work on shot list."""
    for _ in range(5):
        _create_shot(client)
    resp = client.get("/api/shots?limit=2&offset=1")
    assert len(resp.get_json()) == 2


def test_get_shot_not_found(client: FlaskClient) -> None:
    """GET /api/shots/9999 returns 404."""
    assert client.get("/api/shots/9999").status_code == 404


def test_update_shot(client: FlaskClient) -> None:
    """PUT /api/shots/<id> updates fields."""
    shot = _create_shot(client)
    resp = client.put(
        f"/api/shots/{shot['id']}",
        json={"dose_weight": 19.0, "flow_taper": True, "notes": "dial in"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["dose_weight"] == 19.0
    assert body["flow_taper"] is True
    assert body["notes"] == "dial in"


def test_delete_shot(client: FlaskClient) -> None:
    """DELETE /api/shots/<id> returns 204 and removes the shot."""
    shot = _create_shot(client)
    assert client.delete(f"/api/shots/{shot['id']}").status_code == 204
    assert client.get(f"/api/shots/{shot['id']}").status_code == 404


def test_freetext_maker(client: FlaskClient) -> None:
    """Maker accepts any non-empty string, not just the legacy enum values."""
    resp = client.post("/api/shots", json={"date": "2026-03-20", "maker": "Bob"})
    assert resp.status_code == 201
    assert resp.get_json()["maker"] == "Bob"


# ---------------------------------------------------------------------------
# Grind setting validation
# ---------------------------------------------------------------------------


def test_mazzer_valid_grind_setting(client: FlaskClient) -> None:
    """Mazzer accepts the #+# #/# format."""
    grinder_id = _make_mazzer(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "8+5 1/2"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["grind_setting"] == "8+5 1/2"


def test_mazzer_invalid_grind_setting(client: FlaskClient) -> None:
    """Mazzer rejects a bare float as a grind setting."""
    grinder_id = _make_mazzer(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "19.5"},
    )
    assert resp.status_code == 422


def test_option_o_valid_grind_setting(client: FlaskClient) -> None:
    """Option-O accepts a single float."""
    grinder_id = _make_option_o(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "19.5"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["grind_setting"] == "19.5"


def test_option_o_valid_whole_number(client: FlaskClient) -> None:
    """Option-O accepts an integer grind setting."""
    grinder_id = _make_option_o(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "20"},
    )
    assert resp.status_code == 201


def test_option_o_invalid_grind_setting(client: FlaskClient) -> None:
    """Option-O rejects the Mazzer #+# #/# format."""
    grinder_id = _make_option_o(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "8+5 1/2"},
    )
    assert resp.status_code == 422


def test_timemore_valid_grind_setting(client: FlaskClient) -> None:
    """Timemore accepts a single float."""
    grinder_id = _make_timemore(client)
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "15.5"},
    )
    assert resp.status_code == 201


def test_baratza_valid_grind_setting(client: FlaskClient) -> None:
    """Baratza accepts a single float."""
    grinder_id = _make_grinder(client)  # Baratza Vario
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "12.0"},
    )
    assert resp.status_code == 201


def test_baratza_invalid_grind_setting(client: FlaskClient) -> None:
    """Baratza rejects the Mazzer format."""
    grinder_id = _make_grinder(client)  # Baratza Vario
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "8+5 1/2"},
    )
    assert resp.status_code == 422


def test_unknown_grinder_accepts_any_grind_setting(client: FlaskClient) -> None:
    """An unrecognised grinder brand allows any grind setting string."""
    resp = client.post(
        "/api/grinders", json={"make": "Acme", "model": "X1", "type": "blade"}
    )
    grinder_id = resp.get_json()["id"]
    shot_resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grinder_id": grinder_id, "grind_setting": "anything goes"},
    )
    assert shot_resp.status_code == 201


def test_no_grinder_accepts_any_grind_setting(client: FlaskClient) -> None:
    """Without a grinder_id, grind_setting is stored as-is."""
    resp = client.post(
        "/api/shots",
        json={"date": "2026-03-20", "maker": "Scott", "grind_setting": "8+5 1/2"},
    )
    assert resp.status_code == 201


def test_update_shot_grind_setting_validated(client: FlaskClient) -> None:
    """PUT /api/shots/<id> validates grind_setting against the shot's existing grinder."""
    grinder_id = _make_option_o(client)
    shot = _create_shot(client, grinder_id=grinder_id, grind_setting="19.5")
    resp = client.put(f"/api/shots/{shot['id']}", json={"grind_setting": "8+5 1/2"})
    assert resp.status_code == 422


def test_update_shot_valid_grind_setting(client: FlaskClient) -> None:
    """PUT /api/shots/<id> accepts a valid grind_setting update."""
    grinder_id = _make_option_o(client)
    shot = _create_shot(client, grinder_id=grinder_id, grind_setting="19.5")
    resp = client.put(f"/api/shots/{shot['id']}", json={"grind_setting": "20.0"})
    assert resp.status_code == 200
    assert resp.get_json()["grind_setting"] == "20.0"
