"""Grind model training excludes shots pulled with shot profiling (flow_taper)."""

import logging
from datetime import date

import pytest
from flask import Flask
from flask.testing import FlaskClient

from coffee_records.database import get_session
from coffee_records.errors import InsufficientDataError
from coffee_records.models.shot import Shot
from coffee_records.services.grind_model import fit_grind_model, get_grind_model_params
from coffee_records.services.grind_model.eligibility import (
    profiling_flag,
    split_by_profiling,
)

# ── Unit: eligibility split ──────────────────────────────────────────────────


def _shot(shot_id: int, flow_taper: bool | None) -> Shot:
    shot = Shot(id=shot_id, date=date(2026, 3, 1), maker="Scott")
    shot.flow_taper = flow_taper  # type: ignore[assignment]  # None simulates unknown
    return shot


def test_non_profiled_shots_are_eligible() -> None:
    """Shots explicitly marked not profiled stay in the training input."""
    split = split_by_profiling([_shot(1, False), _shot(2, False)])
    assert [s.id for s in split.eligible] == [1, 2]
    assert split.excluded_count == 0


def test_profiled_shots_are_excluded() -> None:
    """Shots explicitly marked profiled are removed."""
    split = split_by_profiling([_shot(1, True)])
    assert split.eligible == []
    assert [s.id for s in split.profiled] == [1]


def test_mixed_input_counts_and_order() -> None:
    """A mixed dataset keeps exactly the non-profiled shots, in order."""
    shots = [_shot(1, False), _shot(2, True), _shot(3, False), _shot(4, None)]
    split = split_by_profiling(shots)
    assert [s.id for s in split.eligible] == [1, 3]
    assert [s.id for s in split.profiled] == [2]
    assert [s.id for s in split.unknown] == [4]
    assert split.excluded_count == 2


def test_unknown_flag_is_excluded_not_coerced() -> None:
    """A missing flag is never treated as 'not profiled' by truthiness."""
    unknown = _shot(1, None)
    assert profiling_flag(unknown) is None
    assert split_by_profiling([unknown]).eligible == []


def test_empty_input() -> None:
    """No shots in, no shots out."""
    split = split_by_profiling([])
    assert (split.eligible, split.profiled, split.unknown) == ([], [], [])


def test_flow_taper_column_is_not_nullable() -> None:
    """The DB enforces a known flag, so 'unknown' only guards in-memory records."""
    assert Shot.__table__.c.flow_taper.nullable is False


# ── Integration: training and plotting ───────────────────────────────────────


def _post(client: FlaskClient, url: str, body: dict[str, object]) -> int:
    resp = client.post(url, json=body)
    assert resp.status_code == 201, resp.get_json()
    return int(resp.get_json()["id"])


def _seed(client: FlaskClient, profiled_days: set[str]) -> tuple[int, int, set[int]]:
    """Two coffees with four days of shots each on one grinder.

    Returns:
        (grinder id, number of shots, ids of profiled shots).
    """
    grinder_id = _post(
        client, "/api/grinders", {"make": "Mazzer", "model": "Mini", "type": "flat"}
    )
    profiled_ids: set[int] = set()
    n_shots = 0
    for name, roasted in (("Alpha", "2026-02-01"), ("Bravo", "2026-02-10")):
        coffee_id = _post(
            client,
            "/api/coffees",
            {"name": name, "roaster": "R", "roast_date": roasted},
        )
        for i, day in enumerate(
            ["2026-03-01", "2026-03-04", "2026-03-07", "2026-03-10"]
        ):
            shot_id = _post(
                client,
                "/api/shots",
                {
                    "date": day,
                    "maker": "Scott",
                    "coffee_id": coffee_id,
                    "grinder_id": grinder_id,
                    "drink_type": "americano",
                    "grind_setting": f"8+{5 - i % 3}",
                    "grinder_temp_before": 62.0 + 3 * i,
                    "dose_weight": 18.0 + 0.5 * i,
                    "final_weight": 38.0 + i,
                    "extraction_time": 26.0 + 2 * i,
                    "flow_taper": day in profiled_days,
                },
            )
            n_shots += 1
            if day in profiled_days:
                profiled_ids.add(shot_id)
    return grinder_id, n_shots, profiled_ids


def test_training_excludes_profiled_shots(
    app: Flask, client: FlaskClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Profiled shots never reach the fit or the plotted training points."""
    # Day 1 is the dialing-in day (always excluded); profile day 4 on both coffees.
    grinder_id, n_shots, profiled_ids = _seed(client, {"2026-03-10"})
    caplog.set_level(logging.INFO)
    with app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)
        with get_session() as session:
            params = get_grind_model_params(session, grinder_id)

    assert result.n_shots_available == n_shots == 8
    # 2 coffees × (4 days − dialing-in day − profiled day) = 4 shots
    assert result.n_shots_used == 4
    assert {p.shot_id for p in params.points}.isdisjoint(profiled_ids)
    assert len(params.points) == 4
    assert "8 candidate shots: 6 eligible, 2 excluded as profiled" in caplog.text


def test_profiling_filter_does_not_shift_dialing_in_day(
    app: Flask, client: FlaskClient
) -> None:
    """If the first day's shots were profiled, day 2 is still a training day."""
    grinder_id, _, _ = _seed(client, {"2026-03-01"})
    with app.app_context():
        with get_session() as session:
            result = fit_grind_model(session, grinder_id)
    # Days 2-4 of both coffees remain: day 1 was excluded once (as dialing-in
    # and profiled), not used to promote day 2 to "first day".
    assert result.n_shots_used == 6


def test_all_profiled_raises_insufficient_data(app: Flask, client: FlaskClient) -> None:
    """When filtering leaves nothing to train on, the error says so clearly."""
    days = {"2026-03-01", "2026-03-04", "2026-03-07", "2026-03-10"}
    grinder_id, _, _ = _seed(client, days)
    with app.app_context():
        with get_session() as session:
            with pytest.raises(InsufficientDataError):
                fit_grind_model(session, grinder_id)
    resp = client.post(f"/api/reports/grind-model/train?grinder_id={grinder_id}")
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "fewer than 3 usable shots after filtering"}
