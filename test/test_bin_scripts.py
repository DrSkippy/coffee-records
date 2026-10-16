"""Tests for the command-line scripts in bin/."""

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))

import backfill_telemetry_thumbnails  # noqa: E402
import create_tables  # noqa: E402
import edit_telemetry  # noqa: E402
import import_ocr_data as ocr  # noqa: E402
import repair_duplicate_coffees  # noqa: E402

from coffee_records.config import Config, ShotDefaultsSeed  # noqa: E402
from coffee_records.database import get_session  # noqa: E402
from coffee_records.models.coffee import Coffee, RoastLevel  # noqa: E402
from coffee_records.models.equipment import (  # noqa: E402
    BrewingDevice,
    Grinder,
    GrinderType,
)
from coffee_records.models.settings import ShotDefaults  # noqa: E402
from coffee_records.models.shot import DrinkType, Shot  # noqa: E402

OCR_FIXTURES = Path(__file__).parent / "fixtures" / "ocr"
TELEMETRY = Path(__file__).parent / "fixtures" / "beanconqueror_flow_profile.json"


# ── import_ocr_data: field parsers ───────────────────────────────────────────


BREWERS = ["sc", "sa", "ot"]


@pytest.mark.parametrize(
    ("raw", "options", "index", "value", "n_warnings"),
    [
        ("(sc)sa ot", BREWERS, 0, "sc", 0),
        ("sc (sa) ot", BREWERS, 1, "sa", 0),
        ("sc sa (xx)", BREWERS, 2, "ot", 1),  # letters disagree: position wins
        ("l 0m d", ["l", "m", "d"], 1, "m", 0),
        ("a b c (d)", ["a", "b", "c"], None, None, 1),  # beyond the options
        ("sc sa ot", BREWERS, None, None, 1),
        ("", BREWERS, None, None, 1),
    ],
)
def test_parse_circled(
    raw: str, options: list[str], index: int | None, value: str | None, n_warnings: int
) -> None:
    """Circled choices decode by position."""
    got_index, got_value, warnings = ocr.parse_circled(raw, options, "ctx")
    assert (got_index, got_value, len(warnings)) == (index, value, n_warnings)


def test_field_parsers() -> None:
    """Dates, floats, drink weights and grind settings parse from OCR noise."""
    assert ocr.parse_date("3/1", 2026) == date(2026, 3, 1)
    assert ocr.parse_date("2/30", 2026) is None
    assert ocr.parse_date("", 2026) is None
    assert ocr.parse_float("~67.5", "temp") == 67.5
    assert ocr.parse_float("40.k") == 40.0
    assert ocr.parse_float(" . ") is None
    assert ocr.parse_float("") is None
    assert ocr.parse_drink_weight("X", (40, 500)) == "shot rejected"
    assert ocr.parse_drink_weight("250g", (40, 500)) == "drink weight: 250g"
    assert ocr.parse_drink_weight("12", (40, 500)) is None
    assert ocr.parse_drink_weight("none", (40, 500)) is None
    assert ocr.parse_drink_weight("", (40, 500)) is None
    assert ocr.normalize_grind(" 8+7 ½ ") == "8+7 1/2"
    assert ocr.infer_grinder_key("8+7") is ocr.EquipmentKey.mazzer
    assert ocr.infer_grinder_key("19.5") is ocr.EquipmentKey.baratza
    assert ocr.infer_grinder_key("weird") is None
    assert ocr.infer_grinder_key("") is None


def test_parse_csv_fixtures() -> None:
    """Fixture sheets parse into typed records, skipping blank/undated rows."""
    coffees = ocr.parse_coffees(OCR_FIXTURES / "coffee_roasters.csv", 2026)
    assert [c.code for c in coffees] == ["A", "B", "D"]
    assert coffees[0].roast_level is RoastLevel.light
    assert coffees[0].roast_date == date(2026, 1, 26)
    assert coffees[2].roast_date is None

    shots = ocr.parse_shots(OCR_FIXTURES / "coffee_shots.csv", ocr.OcrImportSettings())
    assert [s.row for s in shots] == [2, 3, 4]
    first, second, third = shots
    assert first.maker == "Scott"
    assert first.drink_type is DrinkType.americano
    assert first.notes == "shot rejected; bitter"
    assert first.grind_setting == "8+7 1/2"
    assert second.maker == "Sara"
    assert second.notes == "drink weight: 250g"
    assert second.grinder_key is ocr.EquipmentKey.baratza
    assert third.maker == "Unknown"


def test_load_settings(tmp_path: Path) -> None:
    """Settings load from YAML, with defaults when the file is absent."""
    assert ocr.load_settings(tmp_path / "missing.yaml").year == 2026
    path = tmp_path / "s.yaml"
    path.write_text("year: 2025\nbrewers: {xx: Pat}\n")
    settings = ocr.load_settings(path)
    assert settings.year == 2025
    assert settings.brewers == {"xx": "Pat"}
    assert ocr.load_settings(ocr.DEFAULT_SETTINGS_PATH).machine_cutover == date(
        2026, 2, 19
    )


def test_device_key_for() -> None:
    """The machine switches on the cutover date."""
    cutover = date(2026, 2, 19)
    assert ocr.device_key_for(date(2026, 2, 18), cutover) is ocr.EquipmentKey.breville
    assert ocr.device_key_for(cutover, cutover) is ocr.EquipmentKey.ecm


# ── import_ocr_data: database flow ───────────────────────────────────────────


def _seed_equipment_and_coffee() -> None:
    with get_session() as session:
        session.add_all(
            [
                Grinder(make="Mazzer", model="Mini", type=GrinderType.flat),
                BrewingDevice(make="ECM", model="Synchronika", type="espresso"),
                Coffee(
                    name="Ollancey",
                    roaster="Prodigal Coffee",
                    roast_date=date(2026, 1, 26),
                ),
            ]
        )
        session.commit()


def test_import_dry_run_then_apply(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    """Dry run writes nothing; apply inserts new coffees and all shots."""
    settings = ocr.OcrImportSettings()
    coffees = ocr.parse_coffees(OCR_FIXTURES / "coffee_roasters.csv", 2026)
    shots = ocr.parse_shots(OCR_FIXTURES / "coffee_shots.csv", settings)
    with app.app_context():
        _seed_equipment_and_coffee()
        with get_session() as session:
            caplog.set_level(logging.INFO)
            ocr.import_data(coffees, shots, True, session, settings)
            assert "DRY RUN" in caplog.text
            assert "EXISTING id=" in caplog.text  # Ollancay matched Ollancey
            assert "baratza(NOT IN DB)" in caplog.text
            assert session.query(Shot).count() == 0

        with get_session() as session:
            ocr.import_data(coffees, shots, False, session, settings)
        with get_session() as session:
            assert session.query(Coffee).count() == 3  # 1 existing + B + D
            imported = {s.date: s for s in session.query(Shot)}
            mazzer_shot = imported[date(2026, 2, 18)]
            assert mazzer_shot.grinder_id is not None
            assert mazzer_shot.device_id is None  # Breville era, not in DB
            assert imported[date(2026, 2, 19)].device_id is not None  # ECM era
            assert imported[date(2026, 2, 19)].grinder_id is None  # Baratza absent


def test_import_main_dry_run(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The CLI parses files and runs a dry run against the configured DB."""
    monkeypatch.setattr(ocr, "init_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_ocr_data.py",
            "--input-dir",
            str(OCR_FIXTURES),
            "--dry-run",
            "--year",
            "2026",
        ],
    )
    caplog.set_level(logging.INFO)
    with app.app_context():
        ocr.main()
    assert "SUMMARY (dry run)" in caplog.text


def test_import_main_logs_failure(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failures are logged (even in dry-run mode) and exit non-zero."""

    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ocr, "init_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(ocr, "import_data", explode)
    monkeypatch.setattr(
        sys,
        "argv",
        ["import_ocr_data.py", "--input-dir", str(OCR_FIXTURES), "--dry-run"],
    )
    with app.app_context(), pytest.raises(SystemExit) as exit_info:
        ocr.main()
    assert exit_info.value.code == 1
    assert "Import failed" in caplog.text


def test_import_main_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing input files exit with status 1."""
    monkeypatch.setattr(
        sys, "argv", ["import_ocr_data.py", "--input-dir", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as exit_info:
        ocr.main()
    assert exit_info.value.code == 1


# ── edit_telemetry ───────────────────────────────────────────────────────────


def test_edit_telemetry_helpers() -> None:
    """Trimming renumbers brew times; smoothing and clamping edit values."""
    series = [
        {"brew_time": "0.0", "value": 1.0},
        {"brew_time": "1.0", "value": -2.0},
        {"brew_time": "2.0", "value": 6.0},
        {"brew_time": "3.0", "value": 3.0},
    ]
    trimmed = edit_telemetry.trim_series(series, 1.0, 3.0)
    assert [item["brew_time"] for item in trimmed] == ["0.0", "1.0", "2.0"]

    integer_style = [{"brew_time": "4"}]
    edit_telemetry.set_brew_time(integer_style[0], 2.04)
    assert integer_style[0]["brew_time"] == "2"

    assert edit_telemetry.boxcar_smooth([0.0, 3.0, 6.0, 0.0], 3) == [0.0, 3.0, 3.0, 0.0]
    edit_telemetry.apply_smooth(trimmed, "value", 3)
    assert trimmed[1]["value"] == pytest.approx((-2.0 + 6.0 + 3.0) / 3)

    edit_telemetry.clamp_all_fields(trimmed)
    assert trimmed[0]["value"] == 0


def test_edit_telemetry_output_path() -> None:
    """Output names use the shot id and the timestamp in the source filename."""
    source = Path("/x/Beanconqueror_Flowprofile_JSON_08_06_41_20_04_2026.json")
    assert edit_telemetry.parse_shot_datetime(source) is not None
    assert (
        edit_telemetry.make_output_path(source, 7).name
        == "shot_7_2026-04-20_080641.json"
    )
    assert edit_telemetry.make_output_path(Path("/x/a.json"), 7).name == "shot_7.json"
    assert (
        edit_telemetry.make_output_path(Path("/x/a.json"), None).name == "a_edited.json"
    )


def test_edit_telemetry_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI trims, smooths and writes the edited file (plots suppressed)."""
    source = tmp_path / "profile.json"
    source.write_bytes(TELEMETRY.read_bytes())
    monkeypatch.setattr(edit_telemetry, "plot_data", lambda data, title: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "edit_telemetry.py",
            str(source),
            "--start-time",
            "2",
            "--end-time",
            "20",
            "--weight",
            "3",
            "--shot-id",
            "5",
        ],
    )
    edit_telemetry.main()
    edited = json.loads((tmp_path / "shot_5.json").read_text())
    times = [edit_telemetry.get_brew_time(item) for item in edited["weight"]]
    assert min(times) == 0.0
    assert max(times) <= 18.0


# ── create_tables / backfill / repair ────────────────────────────────────────


def test_seed_defaults_is_idempotent(app: Flask) -> None:
    """The defaults row is seeded once from configuration."""
    with app.app_context():
        assert create_tables.seed_defaults(ShotDefaultsSeed(maker="Pat")) is True
        assert create_tables.seed_defaults(ShotDefaultsSeed()) is False
        with get_session() as session:
            row = session.get(ShotDefaults, 1)
            assert row is not None and row.maker == "Pat"


def test_backfill_thumbnails(app: Flask, client: FlaskClient, tmp_path: Path) -> None:
    """Missing thumbnails are generated; existing are skipped; bad files fail."""
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir()
    (telemetry_dir / "good.json").write_bytes(TELEMETRY.read_bytes())
    (telemetry_dir / "bad.json").write_text("{}")
    (telemetry_dir / "done.json").write_bytes(TELEMETRY.read_bytes())
    (telemetry_dir / "done.png").write_bytes(b"existing")
    for name in ("good.json", "bad.json", "done.json"):
        client.post(
            "/api/shots",
            json={"date": "2026-03-01", "maker": "Scott"},
        )
    with app.app_context():
        with get_session() as session:
            for shot, name in zip(
                session.query(Shot).order_by(Shot.id),
                ("good.json", "bad.json", "done.json"),
            ):
                shot.telemetry_filename = name
            session.commit()
        config = Config()
        config.uploads.media_dir = str(tmp_path)
        assert backfill_telemetry_thumbnails.backfill(config) == (1, 1, 1)
        assert (telemetry_dir / "good.png").read_bytes().startswith(b"\x89PNG")
        assert backfill_telemetry_thumbnails.backfill(config, force=True) == (2, 0, 1)


def test_find_duplicate_pair(app: Flask, capsys: pytest.CaptureFixture[str]) -> None:
    """Duplicate clusters resolve to (keeper, duplicate) only when exactly two match."""
    roast = date(2026, 1, 26)
    with app.app_context():
        with get_session() as session:
            assert (
                repair_duplicate_coffees.find_duplicate_pair(
                    session, roast, "ollanc", "prodigal"
                )
                is None
            )
            session.add(Coffee(name="Ollancay", roaster="Prodigal", roast_date=roast))
            session.commit()
            assert (
                repair_duplicate_coffees.find_duplicate_pair(
                    session, roast, "ollanc", "prodigal"
                )
                is None
            )
            session.add(Coffee(name="Ollancey", roaster="Prodigal", roast_date=roast))
            session.commit()
            pair = repair_duplicate_coffees.find_duplicate_pair(
                session, roast, "ollanc", "prodigal"
            )
            assert pair is not None and pair[0].id < pair[1].id
            session.add(Coffee(name="Ollanc", roaster="Prodigal", roast_date=roast))
            session.commit()
            assert (
                repair_duplicate_coffees.find_duplicate_pair(
                    session, roast, "ollanc", "prodigal"
                )
                is None
            )
    output = capsys.readouterr().out
    assert (
        "NOT FOUND" in output
        and "ALREADY CLEAN" in output
        and "manual review" in output
    )
