"""Tests for telemetry thumbnail generation and upload lifecycle."""

import io
import json
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from coffee_records.services.telemetry import (
    TelemetryValidationError,
    parse_brew_time,
    render_telemetry_thumbnail,
)


def _payload(multiplier: float = 1.0) -> bytes:
    data = {
        "weight": [
            {"brew_time": "0.0", "actual_smoothed_weight": 0.0},
            {"brew_time": "0.10", "actual_smoothed_weight": 8.0 * multiplier},
            {"brew_time": "2.0", "actual_smoothed_weight": 16.0 * multiplier},
        ],
        "realtimeFlow": [
            {"brew_time": "0.0", "flow_value": 0.0},
            {"brew_time": "1.0", "flow_value": 2.0 * multiplier},
        ],
        "pressureFlow": [
            {"brew_time": "0.0", "actual_pressure": 0.0},
            {"brew_time": "1.0", "actual_pressure": 9.0 * multiplier},
        ],
    }
    return json.dumps(data).encode()


def test_parse_brew_time_uses_beanconqueror_tenths() -> None:
    assert parse_brew_time("0.10") == 1.0
    assert parse_brew_time("12.3") == 12.3


def test_render_thumbnail_is_expected_png_size() -> None:
    png = render_telemetry_thumbnail(_payload())
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(png[16:20], "big") == 320
    assert int.from_bytes(png[20:24], "big") == 106


@pytest.mark.parametrize("payload", [b"not-json", b"{}", b"[]"])
def test_render_thumbnail_rejects_unusable_data(payload: bytes) -> None:
    with pytest.raises(TelemetryValidationError):
        render_telemetry_thumbnail(payload)


def test_telemetry_upload_replace_failure_and_delete(
    client: FlaskClient, tmp_path: Path
) -> None:
    config = client.application.config["APP_CONFIG"]
    previous_dir = config.uploads.coffee_image_dir
    config.uploads.coffee_image_dir = str(tmp_path)
    try:
        coffee = client.post(
            "/api/coffees", json={"name": "Blend", "roaster": "Roaster"}
        ).get_json()
        coffee_id = coffee["id"]
        image_response = client.post(
            f"/api/coffees/{coffee_id}/image",
            data={"file": (io.BytesIO(b"image"), "label.jpg")},
            content_type="multipart/form-data",
        )
        assert image_response.status_code == 200
        image_filename = image_response.get_json()["image_filename"]

        shot_response = client.post(
            "/api/shots",
            json={"date": "2026-03-20", "maker": "Scott", "coffee_id": coffee_id},
        )
        shot = shot_response.get_json()
        assert shot["coffee_image_filename"] == image_filename

        upload = client.post(
            f"/api/shots/{shot['id']}/telemetry",
            data={"file": (io.BytesIO(_payload()), "telemetry.json")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 200
        uploaded = upload.get_json()
        json_name = uploaded["telemetry_filename"]
        png_name = uploaded["telemetry_thumbnail_filename"]
        telemetry_dir = tmp_path / "telemetry"
        assert (telemetry_dir / json_name).read_bytes() == _payload()
        assert (telemetry_dir / png_name).read_bytes().startswith(b"\x89PNG")

        rejected = client.post(
            f"/api/shots/{shot['id']}/telemetry",
            data={"file": (io.BytesIO(b"bad"), "telemetry.json")},
            content_type="multipart/form-data",
        )
        assert rejected.status_code == 422
        unchanged = client.get(f"/api/shots/{shot['id']}").get_json()
        assert unchanged["telemetry_filename"] == json_name
        assert (telemetry_dir / json_name).exists()
        assert (telemetry_dir / png_name).exists()

        deleted = client.delete(f"/api/shots/{shot['id']}/telemetry")
        assert deleted.status_code == 200
        assert deleted.get_json()["telemetry_thumbnail_filename"] is None
        assert not (telemetry_dir / json_name).exists()
        assert not (telemetry_dir / png_name).exists()
    finally:
        config.uploads.coffee_image_dir = previous_dir
