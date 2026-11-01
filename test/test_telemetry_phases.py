"""Tests for estimating pre-infusion and shot time from telemetry."""

import io
import json
from pathlib import Path

import numpy as np
import pytest
from flask.testing import FlaskClient

from coffee_records.schemas.telemetry import PhaseIssue
from coffee_records.services.brew_time import format_brew_time
from coffee_records.services.telemetry import Series
from coffee_records.services.telemetry_phases import (
    describe_phases,
    estimate_phases,
    estimate_phases_from_payload,
    fit_breakpoint,
)

# Synthetic shot with known phase boundaries (seconds).
PUMP_ON, RAMP, FLOW_ON, PUMP_OFF = 2.0, 9.0, 12.0, 40.0
TIMES = np.round(np.arange(0.0, 45.0, 0.1), 1)


def _pressure(t: float, taper_from: float | None = None) -> float:
    """Ideal pressure: pre-infusion plateau, ramp, eroding plateau, drop."""
    if t < PUMP_ON:
        return 0.0
    if t < PUMP_ON + 1.0:
        return 1.2 * (t - PUMP_ON)
    if t < RAMP:
        return 1.2
    if t < RAMP + 2.0:
        return 1.2 + (9.0 - 1.2) * (t - RAMP) / 2.0
    if t >= PUMP_OFF:
        return 0.0
    natural = 9.0 - 1.5 * (t - RAMP - 2.0) / (PUMP_OFF - RAMP - 2.0)
    if taper_from is not None and t > taper_from:
        return max(1.0, natural - 2.0 * (t - taper_from))
    return natural


def _weight(t: float) -> float:
    """Ideal weight: flat tare, then an accelerating rise from FLOW_ON."""
    if t < FLOW_ON:
        return 0.0
    rise = min(t, PUMP_OFF) - FLOW_ON
    return 0.4 * rise + 0.03 * rise**2


def _series(start: float = 0.0, taper_from: float | None = None) -> dict[str, Series]:
    times = [float(t) for t in TIMES if t >= start]
    return {
        "pressure": [(t, _pressure(t, taper_from)) for t in times],
        "weight": [(t, _weight(t)) for t in times],
    }


def _payload(series: dict[str, Series]) -> bytes:
    return json.dumps(
        {
            "pressureFlow": [
                {"brew_time": format_brew_time(t), "actual_pressure": v}
                for t, v in series["pressure"]
            ],
            "weight": [
                {"brew_time": format_brew_time(t), "actual_smoothed_weight": v}
                for t, v in series["weight"]
            ],
        }
    ).encode()


def test_fit_breakpoint_finds_hinge() -> None:
    t = np.arange(0.0, 10.0, 0.1)
    y = np.where(t < 4.0, 1.0, 1.0 + 2.0 * (t - 4.0))
    assert fit_breakpoint(t, y, 0.05) == pytest.approx(4.0, abs=0.06)
    assert fit_breakpoint(t[:4], y[:4], 0.05) is None


def test_estimates_known_boundaries_of_a_natural_shot() -> None:
    phases = estimate_phases(_series())
    assert phases.t_pump_on == pytest.approx(PUMP_ON, abs=0.3)
    assert phases.t_ramp == pytest.approx(RAMP, abs=0.3)
    assert phases.t_flow_on == pytest.approx(FLOW_ON, abs=0.3)
    assert phases.t_pump_off == pytest.approx(PUMP_OFF, abs=0.3)
    assert phases.pre_infusion_s == pytest.approx(FLOW_ON - PUMP_ON, abs=0.5)
    assert phases.shot_time_s == pytest.approx(PUMP_OFF - FLOW_ON, abs=0.5)
    assert not phases.pump_on_imputed
    assert phases.profiled is False
    assert phases.issues == []


def test_auto_start_recording_imputes_pump_on() -> None:
    phases = estimate_phases(_series(start=4.0))
    assert phases.pump_on_imputed
    assert phases.recording_start_bar == pytest.approx(1.2)
    assert phases.t_pump_on == pytest.approx(4.0 - 2.65)
    assert phases.shot_time_s == pytest.approx(PUMP_OFF - FLOW_ON, abs=0.5)
    assert "pump on estimated, recording started at 1.20 bar" in "\n".join(
        describe_phases(phases)
    )


def test_truncated_recording_reports_na() -> None:
    phases = estimate_phases(_series(start=15.0))
    assert phases.issues == [PhaseIssue.truncated_start]
    assert phases.pre_infusion_s is None and phases.shot_time_s is None
    assert describe_phases(phases)[1].startswith(
        "Pre-infusion and shot time: n/a (recording started mid-shot"
    )


def test_profiled_shot_is_cut_at_the_real_pump_off() -> None:
    phases = estimate_phases(_series(taper_from=25.0))
    assert phases.t_pump_off == pytest.approx(PUMP_OFF, abs=0.3)
    assert phases.profiled is True
    assert phases.end_ratio is not None and phases.end_ratio < 0.2
    assert "Pressure profile: profiled" in "\n".join(describe_phases(phases))


def test_missing_pressure_reports_na() -> None:
    phases = estimate_phases({"weight": _series()["weight"]})
    assert phases.issues == [PhaseIssue.no_pressure]
    assert describe_phases(phases)[1] == (
        "Pre-infusion and shot time: n/a (no pressure data)"
    )


def test_payload_round_trip_matches_series() -> None:
    phases = estimate_phases_from_payload(_payload(_series()))
    assert phases.shot_time_s == pytest.approx(PUMP_OFF - FLOW_ON, abs=0.5)
    text = "\n".join(describe_phases(phases))
    assert "Shot time:" in text and "natural decline" in text


def test_phases_endpoint(client: FlaskClient, tmp_path: Path) -> None:
    config = client.application.config["APP_CONFIG"]
    previous_dir = config.uploads.media_dir
    config.uploads.media_dir = str(tmp_path)
    try:
        shot = client.post(
            "/api/shots", json={"date": "2026-11-01", "maker": "Scott"}
        ).get_json()
        url = f"/api/shots/{shot['id']}/telemetry/phases"
        assert client.get(url).status_code == 404
        assert client.get("/api/shots/9999/telemetry/phases").status_code == 404

        uploaded = client.post(
            f"/api/shots/{shot['id']}/telemetry",
            data={"file": (io.BytesIO(_payload(_series())), "t.json")},
            content_type="multipart/form-data",
        ).get_json()
        response = client.get(url)
        assert response.status_code == 200
        body = response.get_json()
        assert body["shot_time_s"] == pytest.approx(PUMP_OFF - FLOW_ON, abs=0.5)
        assert body["profiled"] is False

        stored = tmp_path / "telemetry" / uploaded["telemetry_filename"]
        stored.write_text("not json")
        assert client.get(url).status_code == 422
        stored.unlink()
        assert client.get(url).status_code == 404
    finally:
        config.uploads.media_dir = previous_dir
