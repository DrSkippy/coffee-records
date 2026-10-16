"""API tests for error mapping, parameter validation, uploads and file cleanup."""

from collections.abc import Generator
from io import BytesIO
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from coffee_records.config import Config

TELEMETRY = (
    Path(__file__).parent / "fixtures" / "beanconqueror_flow_profile.json"
).read_bytes()


@pytest.fixture()
def media_dir(app: Flask, tmp_path: Path) -> Generator[Path, None, None]:
    """Point uploads at a temporary directory for one test."""
    config: Config = app.config["APP_CONFIG"]
    previous = config.uploads.media_dir
    config.uploads.media_dir = str(tmp_path)
    yield tmp_path
    config.uploads.media_dir = previous


def _coffee(client: FlaskClient, **extra: object) -> int:
    body: dict[str, object] = {"name": "Alpha", "roaster": "R"} | extra
    return int(client.post("/api/coffees", json=body).get_json()["id"])


def _shot(client: FlaskClient, **extra: object) -> int:
    body: dict[str, object] = {"date": "2026-03-01", "maker": "Scott"} | extra
    resp = client.post("/api/shots", json=body)
    assert resp.status_code == 201, resp.get_json()
    return int(resp.get_json()["id"])


def _upload(data: bytes, filename: str) -> dict[str, object]:
    return {"file": (BytesIO(data), filename)}


# ── Query parameter validation (400 instead of 500) ──────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "/api/reports/dose-yield?coffee_id=abc",
        "/api/reports/shots-per-day?date_from=yesterday",
        "/api/reports/extraction-trends?device_id=1.5",
        "/api/reports/shots-per-grinder?date_to=2026-13-01",
        "/api/reports/grind-regression?coffee_id=1&grinder_id=x",
        "/api/reports/target-shot-time?coffee_id=nope",
        "/api/reports/grind-model/params?grinder_id=1&training_id=t",
        "/api/reports/grind-model/params?grinder_id=1&as_of=soon",
        "/api/reports/by-coffee/1?date_from=bad",
        "/api/shots?date_from=bad",
        "/api/shots?limit=many",
    ],
)
def test_malformed_query_params_return_400(client: FlaskClient, url: str) -> None:
    """Unparseable query parameters are client errors, not server errors."""
    resp = client.get(url)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_required_param_missing(client: FlaskClient) -> None:
    """Missing required ids keep their original messages."""
    resp = client.get("/api/reports/grind-regression")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "coffee_id required"}


# ── Grind regression error paths ─────────────────────────────────────────────


def test_grind_regression_unknown_coffee(client: FlaskClient) -> None:
    """Unknown coffees are 404."""
    resp = client.get("/api/reports/grind-regression?coffee_id=999")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "coffee not found"}


def test_grind_regression_no_roast_date(client: FlaskClient) -> None:
    """Coffees without a roast date can't be regressed on age."""
    coffee_id = _coffee(client)
    resp = client.get(f"/api/reports/grind-regression?coffee_id={coffee_id}")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "coffee has no roast_date"}


def test_grind_regression_insufficient(client: FlaskClient) -> None:
    """Fewer than min_points usable shots is 422."""
    coffee_id = _coffee(client, roast_date="2026-02-01")
    resp = client.get(f"/api/reports/grind-regression?coffee_id={coffee_id}")
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "fewer than 3 usable data points"}


def test_grind_regression_skips_singular_grinder(client: FlaskClient) -> None:
    """A grinder whose temperature never varies is skipped (then 422)."""
    grinder_id = int(
        client.post(
            "/api/grinders", json={"make": "Baratza", "model": "V", "type": "conical"}
        ).get_json()["id"]
    )
    coffee_id = _coffee(client, roast_date="2026-02-01")
    for day, grind in (
        ("2026-02-05", "15"),
        ("2026-02-07", "16"),
        ("2026-02-09", "17"),
    ):
        _shot(
            client,
            date=day,
            coffee_id=coffee_id,
            grinder_id=grinder_id,
            grind_setting=grind,
            grinder_temp_before=65.0,
        )
    url = f"/api/reports/grind-regression?coffee_id={coffee_id}&grinder_id={grinder_id}"
    assert client.get(url).status_code == 422


# ── Equipment CRUD errors ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("grinders", "Grinder"),
        ("brewing-devices", "Brewing device"),
        ("scales", "Scale"),
    ],
)
def test_equipment_not_found(client: FlaskClient, path: str, label: str) -> None:
    """Every equipment route reports a typed 404."""
    for method in (client.get, client.delete):
        resp = method(f"/api/{path}/999")
        assert resp.status_code == 404
        assert resp.get_json() == {"error": f"{label} not found"}
    resp = client.put(f"/api/{path}/999", json={"notes": "x"})
    assert resp.status_code == 404


def test_device_delete_conflict(client: FlaskClient) -> None:
    """Devices referenced by shots can't be deleted."""
    device_id = int(
        client.post(
            "/api/brewing-devices",
            json={"make": "ECM", "model": "S", "type": "espresso"},
        ).get_json()["id"]
    )
    _shot(client, device_id=device_id)
    resp = client.delete(f"/api/brewing-devices/{device_id}")
    assert resp.status_code == 409
    assert resp.get_json() == {
        "error": "Cannot delete: 1 shot(s) reference this device"
    }


# ── Shots ────────────────────────────────────────────────────────────────────


def test_update_shot_validates_grind_against_current_grinder(
    client: FlaskClient,
) -> None:
    """Changing only the grind setting checks it against the shot's grinder."""
    grinder_id = int(
        client.post(
            "/api/grinders", json={"make": "Mazzer", "model": "Mini", "type": "flat"}
        ).get_json()["id"]
    )
    shot_id = _shot(client, grinder_id=grinder_id, grind_setting="8+5")
    resp = client.put(f"/api/shots/{shot_id}", json={"grind_setting": "19.5"})
    assert resp.status_code == 422
    resp = client.put(f"/api/shots/{shot_id}", json={"grind_setting": "8+6 1/2"})
    assert resp.status_code == 200
    assert resp.get_json()["grind_setting"] == "8+6 1/2"


def test_shot_not_found_routes(client: FlaskClient) -> None:
    """Missing shots are 404 across routes."""
    assert client.put("/api/shots/999", json={}).status_code == 404
    assert client.delete("/api/shots/999").status_code == 404
    assert client.delete("/api/shots/999/video").status_code == 404
    assert client.delete("/api/shots/999/telemetry").status_code == 404


@pytest.mark.parametrize("route", ["video", "telemetry", "import-csv"])
def test_upload_requires_file(client: FlaskClient, route: str) -> None:
    """Uploads without a file part, or with an empty filename, are 400."""
    url = "/api/shots/import-csv" if route == "import-csv" else f"/api/shots/1/{route}"
    assert client.post(url, data={}).status_code == 400
    resp = client.post(url, data=_upload(b"x", ""), content_type="multipart/form-data")
    assert resp.status_code == 400


def test_import_csv_rejects_non_utf8(client: FlaskClient) -> None:
    """Binary uploads produce a 422 with a clear message."""
    resp = client.post(
        "/api/shots/import-csv",
        data=_upload(b"\xff\xfe\x00bad", "shot.csv"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "CSV must be UTF-8 text"}


def test_video_upload_replace_and_delete(client: FlaskClient, media_dir: Path) -> None:
    """Replacing a video deletes the old file only after the new one is saved."""
    shot_id = _shot(client)
    first = client.post(
        f"/api/shots/{shot_id}/video",
        data=_upload(b"v1", "clip.MOV"),
        content_type="multipart/form-data",
    ).get_json()["video_filename"]
    assert first.endswith(".mov")
    second = client.post(
        f"/api/shots/{shot_id}/video",
        data=_upload(b"v2", "clip.exe"),
        content_type="multipart/form-data",
    ).get_json()["video_filename"]
    assert second.endswith(".mp4")
    assert not (media_dir / first).exists()
    assert (media_dir / second).read_bytes() == b"v2"

    resp = client.delete(f"/api/shots/{shot_id}/video")
    assert resp.get_json()["video_filename"] is None
    assert not (media_dir / second).exists()


def test_delete_shot_removes_media_after_commit(
    client: FlaskClient, media_dir: Path
) -> None:
    """Deleting a shot removes its video and telemetry files."""
    shot_id = _shot(client)
    video = client.post(
        f"/api/shots/{shot_id}/video",
        data=_upload(b"v", "a.mp4"),
        content_type="multipart/form-data",
    ).get_json()["video_filename"]
    telemetry = client.post(
        f"/api/shots/{shot_id}/telemetry",
        data=_upload(TELEMETRY, "t.json"),
        content_type="multipart/form-data",
    ).get_json()["telemetry_filename"]
    assert client.delete(f"/api/shots/{shot_id}").status_code == 204
    assert not (media_dir / video).exists()
    assert not (media_dir / "telemetry" / telemetry).exists()


def test_failed_commit_keeps_existing_media(
    client: FlaskClient, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the DB commit fails, the new file is removed and the old one kept."""
    shot_id = _shot(client)
    first = client.post(
        f"/api/shots/{shot_id}/video",
        data=_upload(b"v1", "a.mp4"),
        content_type="multipart/form-data",
    ).get_json()["video_filename"]

    def failing_commit(self: Session) -> None:
        raise OperationalError("COMMIT", {}, Exception("db down"))

    monkeypatch.setattr(Session, "commit", failing_commit)
    with pytest.raises(SQLAlchemyError):
        client.post(
            f"/api/shots/{shot_id}/video",
            data=_upload(b"v2", "b.mp4"),
            content_type="multipart/form-data",
        )
    assert sorted(p.name for p in media_dir.iterdir()) == [first]


# ── Coffee images ────────────────────────────────────────────────────────────


def test_coffee_image_lifecycle(client: FlaskClient, media_dir: Path) -> None:
    """Upload, replace and remove a coffee label image."""
    coffee_id = _coffee(client)
    url = f"/api/coffees/{coffee_id}/image"
    first = client.post(
        url, data=_upload(b"i1", "a.PNG"), content_type="multipart/form-data"
    ).get_json()["image_filename"]
    assert first.endswith(".png")
    second = client.post(
        url, data=_upload(b"i2", "b.bmp"), content_type="multipart/form-data"
    ).get_json()["image_filename"]
    assert second.endswith(".jpg")
    assert not (media_dir / first).exists()

    assert client.delete(url).get_json()["image_filename"] is None
    assert not (media_dir / second).exists()
    # Deleting again is a no-op
    assert client.delete(url).status_code == 200


def test_coffee_image_errors(client: FlaskClient) -> None:
    """Image routes validate the upload and the coffee id."""
    assert client.post("/api/coffees/1/image", data={}).status_code == 400
    resp = client.post(
        "/api/coffees/999/image",
        data=_upload(b"i", "a.jpg"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404
    assert client.delete("/api/coffees/999/image").status_code == 404


def test_coffee_update_and_delete_conflict(client: FlaskClient) -> None:
    """Coffee update applies partial fields; referenced coffees can't be deleted."""
    coffee_id = _coffee(client)
    resp = client.put(f"/api/coffees/{coffee_id}", json={"roaster": "New"})
    assert resp.get_json()["roaster"] == "New"
    assert resp.get_json()["name"] == "Alpha"
    _shot(client, coffee_id=coffee_id)
    assert client.delete(f"/api/coffees/{coffee_id}").status_code == 409
    assert client.put("/api/coffees/999", json={}).status_code == 404


# ── Defaults and health ──────────────────────────────────────────────────────


def test_defaults_reject_unknown_drink_type(client: FlaskClient) -> None:
    """drink_type is validated against DrinkType."""
    resp = client.put("/api/defaults", json={"maker": "Scott", "drink_type": "mocha"})
    assert resp.status_code == 422


def test_defaults_upsert_when_missing(client: FlaskClient) -> None:
    """PUT creates the singleton row when it doesn't exist yet."""
    resp = client.put("/api/defaults", json={"maker": "Sara", "drink_type": "latte"})
    assert resp.status_code == 200
    assert resp.get_json()["maker"] == "Sara"
    assert client.get("/api/defaults").get_json()["drink_type"] == "latte"


def test_health_reports_database_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing database is reported (and logged) rather than raised."""

    def failing_execute(self: Session, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(Session, "execute", failing_execute)
    assert client.get("/health").get_json() == {"status": "ok", "database": "error"}


def test_health_ok(client: FlaskClient) -> None:
    """Healthy database reports ok."""
    assert client.get("/health").get_json() == {"status": "ok", "database": "ok"}
