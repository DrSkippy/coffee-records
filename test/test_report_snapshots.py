"""Golden-output tests: report endpoints must keep producing the same numbers.

The snapshot in ``fixtures/report_snapshots.json`` was recorded from the
pre-refactor implementation. Regenerate deliberately with::

    UPDATE_SNAPSHOTS=1 poetry run pytest test/test_report_snapshots.py
"""

import json
import os
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "report_snapshots.json"
ID_KEYS = {"coffee_id", "shot_id", "grinder_id", "device_id", "training_id"}
VOLATILE_KEYS = {"trained_at"}
RANGE = "date_from=2026-01-01&date_to=2026-12-31"


def _post(client: FlaskClient, url: str, body: dict[str, Any]) -> int:
    resp = client.post(url, json=body)
    assert resp.status_code == 201, resp.get_json()
    return int(resp.get_json()["id"])


def _seed(client: FlaskClient) -> dict[str, int]:
    """Create a deterministic multi-coffee, multi-grinder dataset.

    Returns:
        Mapping of real database id → stable ordinal, for normalisation.
    """
    rng = random.Random(20260415)
    mazzer = _post(
        client, "/api/grinders", {"make": "Mazzer", "model": "Mini", "type": "flat"}
    )
    baratza = _post(
        client,
        "/api/grinders",
        {"make": "Baratza", "model": "Virtuoso+", "type": "conical"},
    )
    ecm = _post(
        client,
        "/api/brewing-devices",
        {"make": "ECM", "model": "Synchronika", "type": "espresso"},
    )
    breville = _post(
        client,
        "/api/brewing-devices",
        {"make": "Breville", "model": "Bambino", "type": "espresso"},
    )
    coffees = [
        _post(
            client,
            "/api/coffees",
            {"name": name, "roaster": "Roaster", "roast_date": roasted},
        )
        for name, roasted in (
            ("Alpha", "2026-02-01"),
            ("Bravo", "2026-02-20"),
            ("Charlie", "2026-03-05"),
        )
    ]
    drinks = ["americano", "latte", "cappuccino", "drip"]
    start = date(2026, 2, 5)
    for i in range(60):
        coffee_index = i % 3
        day = start + timedelta(days=i // 2 + coffee_index * 7)
        temp = round(60 + rng.uniform(0, 14), 1)
        dose = round(rng.choice([18.0, 18.5, 19.0, 20.0, 20.5]), 1)
        ratio = rng.uniform(1.8, 2.3)
        on_mazzer = i % 5 != 4
        age = (day - date(2026, 2, 1)).days
        if on_mazzer:
            fine = 85 - 0.08 * age + 0.2 * (temp - 65) + rng.uniform(-0.6, 0.6)
            coarse, rest = divmod(fine, 10)
            quarter = round((rest - int(rest)) * 4) / 4
            grind = f"{int(coarse)}+{int(rest)}" + (
                {0.25: " 1/4", 0.5: " 1/2", 0.75: " 3/4"}.get(quarter, "")
            )
        else:
            grind = f"{round(15 + rng.uniform(0, 5), 1)}"
        _post(
            client,
            "/api/shots",
            {
                "date": day.isoformat(),
                "maker": "Scott",
                "coffee_id": coffees[coffee_index],
                "grinder_id": mazzer if on_mazzer else baratza,
                "device_id": ecm if i % 4 else breville,
                "drink_type": drinks[i % 7 % 4],
                "dose_weight": dose,
                "final_weight": round(dose * ratio, 1),
                "extraction_time": round(24 + rng.uniform(0, 10), 1),
                "extraction_delta": rng.choice([0.0, 0.0, 1.5, -2.0]),
                "grinder_temp_before": temp,
                "grind_setting": grind,
            },
        )
    ordinals = {"mazzer": mazzer, "baratza": baratza, "ecm": ecm, "breville": breville}
    ordinals |= {f"coffee{n}": cid for n, cid in enumerate(coffees)}
    return ordinals


def _normalize(value: Any) -> Any:
    """Drop volatile keys and replace database ids with their sort rank."""
    if isinstance(value, dict):
        return {
            key: ("<id>" if key in ID_KEYS and item is not None else _normalize(item))
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _collect(client: FlaskClient, ids: dict[str, int]) -> dict[str, Any]:
    """Call every report endpoint and return normalised JSON keyed by name."""
    coffee0, mazzer, ecm = ids["coffee0"], ids["mazzer"], ids["ecm"]
    urls = {
        "dose_yield": f"/api/reports/dose-yield?{RANGE}",
        "dose_yield_filtered": f"/api/reports/dose-yield?{RANGE}&grinder_id={mazzer}&device_id={ecm}",
        "shots_per_day": f"/api/reports/shots-per-day?{RANGE}&coffee_id={coffee0}",
        "extraction_trends": f"/api/reports/extraction-trends?{RANGE}",
        "shots_per_grinder": f"/api/reports/shots-per-grinder?{RANGE}",
        "by_coffee": f"/api/reports/by-coffee/{coffee0}?{RANGE}",
        "target_shot_time": f"/api/reports/target-shot-time?coffee_id={coffee0}&grinder_id={mazzer}",
        "grind_regression_default": f"/api/reports/grind-regression?coffee_id={coffee0}",
        "grind_regression_baratza": f"/api/reports/grind-regression?coffee_id={ids['coffee1']}&grinder_id={ids['baratza']}",
    }
    results: dict[str, Any] = {}
    for name, url in urls.items():
        resp = client.get(url)
        results[name] = {"status": resp.status_code, "body": resp.get_json()}
    train = client.post(f"/api/reports/grind-model/train?grinder_id={mazzer}")
    results["grind_model_train"] = {
        "status": train.status_code,
        "body": train.get_json(),
    }
    params = client.get(f"/api/reports/grind-model/params?grinder_id={mazzer}")
    results["grind_model_params"] = {
        "status": params.status_code,
        "body": params.get_json(),
    }
    return {key: _normalize(value) for key, value in results.items()}


def _assert_matches(actual: Any, expected: Any, path: str = "") -> None:
    """Recursively compare JSON, allowing float noise below 1e-6."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_matches(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for index, (got, want) in enumerate(zip(actual, expected)):
            _assert_matches(got, want, f"{path}[{index}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=1e-6, abs=1e-6), path
    else:
        assert actual == expected, path


def test_report_outputs_match_snapshot(client: FlaskClient) -> None:
    """Every report endpoint reproduces the recorded outputs."""
    results = _collect(client, _seed(client))
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(json.dumps(results, indent=1, sort_keys=True))
        pytest.skip("snapshot written")
    _assert_matches(results, json.loads(SNAPSHOT_PATH.read_text()))
