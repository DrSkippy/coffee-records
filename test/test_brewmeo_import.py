"""Tests for importing Brewmeo shot CSVs."""

import io
import json
from collections.abc import Generator
from datetime import date, datetime
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import coffee_records.models  # noqa: F401  (registers tables)
from coffee_records.database import Base
from coffee_records.models.coffee import Coffee, RoastLevel
from coffee_records.models.equipment import BrewingDevice, Grinder, GrinderType
from coffee_records.services.brewmeo_import import (
    BrewmeoImportError,
    build_import,
    compose_notes,
    derive_flow,
    format_brew_time,
    parse_brewmeo_csv,
    to_telemetry_json,
    trim_weight_disturbance,
)
from coffee_records.services.matching import best_equipment_match
from coffee_records.services.telemetry import (
    extract_thumbnail_series,
    parse_brew_time,
    render_telemetry_thumbnail,
)

FIXTURE = Path(__file__).parent / "fixtures" / "brewmeo_shot.csv"
SAMPLE_JSON = (
    Path(__file__).parent.parent
    / "sample_data"
    / "Beanconqueror_Flowprofile_JSON_08_06_41_20_04_2026.json"
)


@pytest.fixture()
def csv_text() -> str:
    """Return the trimmed Brewmeo export fixture."""
    return FIXTURE.read_text()


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Isolated in-memory database seeded like production equipment."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Grinder(
                    make="Mazzer",
                    model="Mazzer Mini Espresso Coffee Grinder",
                    type=GrinderType.flat,
                ),
                Grinder(
                    make="Baratza",
                    model="Baratza Virtuoso+ Coffee Grinder",
                    type=GrinderType.conical,
                ),
                Grinder(make="Option-O", model="LAGOM P80", type=GrinderType.flat),
                BrewingDevice(
                    make="ECM",
                    model="ECM Synchronika II Espresso Machine",
                    type="espresso",
                ),
                BrewingDevice(
                    make="Breville", model="Dual Boiler (BE920)", type="espresso"
                ),
            ]
        )
        session.commit()
        yield session


def _add_sidama(session: Session, roast_date: date) -> Coffee:
    coffee = Coffee(
        name="Sweet Sidama",
        roaster="Flatlands Coffee",
        roast_date=roast_date,
        roast_level=RoastLevel.light,
        origin_country="Ethiopia",
        process="Natural",
    )
    session.add(coffee)
    session.commit()
    return coffee


def test_parse_reads_meta_and_samples(csv_text: str) -> None:
    """Meta rows (including one with a stray trailing comma) and samples parse."""
    shot = parse_brewmeo_csv(csv_text)
    assert shot.text("Name") == "My shot #19"
    assert shot.text("Unit system") == "metric"
    assert shot.positive("Dose") is None
    assert shot.positive("Weight") == pytest.approx(40.305, abs=1e-3)
    assert shot.weight and shot.pressure and shot.temperature
    assert shot.weight == sorted(shot.weight)


@pytest.mark.parametrize(
    "text",
    ["", "a,b,c\n1,2,3\n", "information_type,elapsed\nmoment,1\n"],
)
def test_parse_rejects_non_brewmeo_csv(text: str) -> None:
    """Files without Brewmeo columns are rejected."""
    with pytest.raises(BrewmeoImportError):
        parse_brewmeo_csv(text)


def test_parse_requires_meta_rows(csv_text: str) -> None:
    """A CSV with samples but no metadata is rejected."""
    lines = [line for line in csv_text.splitlines() if not line.startswith("meta,")]
    with pytest.raises(BrewmeoImportError, match="metadata"):
        parse_brewmeo_csv("\n".join(lines))


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(0.005, "0.0"), (0.96, "1.0"), (10.04, "10.0"), (37.908, "37.9")],
)
def test_format_brew_time_uses_tenths(elapsed: float, expected: str) -> None:
    """Brew time round-trips through the Beanconqueror S.T parser."""
    assert format_brew_time(elapsed) == expected
    assert parse_brew_time(expected) == pytest.approx(elapsed, abs=0.05)


def test_telemetry_json_is_plottable_with_metadata(csv_text: str) -> None:
    """Converted telemetry passes the thumbnail validator and carries metadata."""
    shot = parse_brewmeo_csv(csv_text)
    telemetry = to_telemetry_json(shot, "My shot #19.csv")
    payload = json.dumps(telemetry).encode()

    assert set(extract_thumbnail_series(payload)) == {"weight", "flow", "pressure"}
    assert render_telemetry_thumbnail(payload).startswith(b"\x89PNG")
    metadata = telemetry["metadata"]
    assert metadata["source_file"] == "My shot #19.csv"
    assert metadata["shot"]["name"] == "My shot #19"
    assert metadata["meta"]["Basket Name"] == "VST 18 g"
    assert telemetry["weight"][0]["timestamp"] == "06:29:10.633"
    assert len(telemetry["temperatureFlow"]) == len(shot.temperature)


def test_derived_flow_matches_reported_average(csv_text: str) -> None:
    """Mean derived flow agrees with Brewmeo's own average flow rate."""
    shot = parse_brewmeo_csv(csv_text)
    flow = derive_flow(shot.weight)
    values = [f for _, _, f in flow]
    assert min(values) >= 0
    assert sum(values) / len(values) == pytest.approx(
        shot.positive("Avarage flow rate"), rel=0.05
    )


def test_derive_flow_needs_two_samples() -> None:
    """Too little data yields no flow series."""
    assert derive_flow([(1.0, 5.0)]) == []


def test_trim_weight_disturbance_only_at_tail() -> None:
    """A lifted cup at the end is trimmed; the same jump mid-shot is kept."""
    steady = [(t / 10, t / 10) for t in range(0, 300)]
    lifted = steady + [(30.0, 60.0), (30.1, 20.0)]
    kept, trimmed_from = trim_weight_disturbance(lifted)
    assert kept == steady
    assert trimmed_from == pytest.approx(30.0)

    early = steady[:50] + [(5.0, 40.0)] + [(t / 10, 40.0) for t in range(51, 300)]
    assert trim_weight_disturbance(early) == (early, None)


def test_existing_beanconqueror_json_still_plots() -> None:
    """Regression: real Beanconqueror exports parse exactly as before."""
    series = extract_thumbnail_series(SAMPLE_JSON.read_bytes())
    assert set(series) == {"weight", "flow", "pressure"}
    assert render_telemetry_thumbnail(SAMPLE_JSON.read_bytes()).startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Lagom Option O p80", 3),
        ("ECM Synchronika II", 4),
        ("Unknown Brand Coffee Grinder", None),
        ("", None),
    ],
)
def test_best_equipment_match(label: str, expected: int | None) -> None:
    """Punctuation and generic words don't affect equipment matching."""
    candidates = [
        (1, "Mazzer Mazzer Mini Espresso Coffee Grinder"),
        (2, "Baratza Baratza Virtuoso+ Coffee Grinder"),
        (3, "Option-O LAGOM P80"),
        (4, "ECM ECM Synchronika II Espresso Machine"),
    ]
    assert best_equipment_match(label, candidates) == expected


def test_build_import_new_bag_when_roast_date_differs(
    db: Session, csv_text: str
) -> None:
    """Same beans with a different roast date propose a new coffee."""
    _add_sidama(db, date(2026, 8, 6))
    result = build_import(db, parse_brewmeo_csv(csv_text), "My shot #19.csv")

    assert result.fields.coffee_id is None
    assert result.new_coffee is not None
    assert result.new_coffee.roast_date == date(2026, 8, 24)
    assert result.new_coffee.roast_level == RoastLevel.light
    assert result.new_coffee.variety == "Heirloom"
    assert result.new_coffee.origin_country == "Ethiopia"
    assert result.fields.grinder_id is not None
    assert result.fields.device_id is not None
    assert result.fields.date == date(2026, 9, 26)
    assert result.fields.recorded_at == datetime(2026, 9, 26, 6, 29, 10, 628000)
    assert result.fields.maker is None
    assert result.fields.extraction_time == 37.9
    assert result.fields.grind_setting == "0.8"
    assert result.fields.dose_weight is None
    assert result.telemetry is not None
    assert result.telemetry_filename == "my-shot-19.json"
    assert result.warnings == []
    assert db.query(Coffee).count() == 1


def test_build_import_matches_existing_coffee(db: Session, csv_text: str) -> None:
    """Name, roaster and roast date agreement selects the existing coffee."""
    coffee = _add_sidama(db, date(2026, 8, 24))
    result = build_import(db, parse_brewmeo_csv(csv_text), "shot.csv")
    assert result.fields.coffee_id == coffee.id
    assert result.new_coffee is None


def test_build_import_warns_on_unknown_equipment(csv_text: str) -> None:
    """Unmatched equipment is left unselected, warned about, and kept in notes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = build_import(session, parse_brewmeo_csv(csv_text), "shot.csv")
    assert result.fields.grinder_id is None
    assert result.fields.device_id is None
    assert any("Grinder 'Lagom Option O p80'" in w for w in result.warnings)
    assert "Grinder Name: Lagom Option O p80" in result.notes
    assert "Espresso Machine Name: ECM Synchronika II" in result.notes


def test_compose_notes_includes_only_unmatched_info(csv_text: str) -> None:
    """Notes list unmatched values but skip ids, boilerplate and zeros."""
    shot = parse_brewmeo_csv(csv_text)
    notes = compose_notes(shot, {"Name", "Weight", "Beans", "Grinder Setting"})
    lines = notes.splitlines()
    assert lines[0] == "Imported from Brewmeo: My shot #19"
    assert "Basket Name: VST 18 g" in lines
    assert "Tamper Force: 30 kg" in lines
    assert "Average flow rate: 1.06 g/s" in lines
    assert not any(line.startswith("Brew ratio") for line in lines)
    for absent in ("Beans Id", "Software", "Url", "Dose", "Weight:", "Sweet Sidama"):
        assert absent not in notes


def test_import_endpoint_returns_prefill_without_writing(
    client: FlaskClient, csv_text: str
) -> None:
    """The endpoint parses the CSV and leaves the database unchanged."""
    coffees_before = len(client.get("/api/coffees").get_json())
    shots_before = len(client.get("/api/shots").get_json())

    response = client.post(
        "/api/shots/import-csv",
        data={"file": (io.BytesIO(csv_text.encode()), "My shot #19.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["source"] == "My shot #19.csv"
    assert body["fields"]["final_weight"] == pytest.approx(40.305, abs=1e-3)
    assert body["new_coffee"]["name"] == "Sweet Sidama"
    assert body["notes"].startswith("Imported from Brewmeo")
    assert "realtimeFlow" in body["telemetry"]
    assert len(client.get("/api/coffees").get_json()) == coffees_before
    assert len(client.get("/api/shots").get_json()) == shots_before


def test_import_endpoint_errors(client: FlaskClient) -> None:
    """Missing, non-UTF-8 and non-Brewmeo uploads are rejected."""
    assert client.post("/api/shots/import-csv").status_code == 400
    for payload in (b"\xff\xfe\x00bad", b"a,b\n1,2\n"):
        response = client.post(
            "/api/shots/import-csv",
            data={"file": (io.BytesIO(payload), "shot.csv")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 422


def test_imported_telemetry_saves_like_an_upload(
    client: FlaskClient, csv_text: str, tmp_path: Path
) -> None:
    """End to end: import, create shot, upload the returned telemetry."""
    config = client.application.config["APP_CONFIG"]
    previous_dir = config.uploads.coffee_image_dir
    config.uploads.coffee_image_dir = str(tmp_path)
    try:
        body = client.post(
            "/api/shots/import-csv",
            data={"file": (io.BytesIO(csv_text.encode()), "My shot #19.csv")},
            content_type="multipart/form-data",
        ).get_json()
        coffee = client.post("/api/coffees", json=body["new_coffee"]).get_json()
        fields = {k: v for k, v in body["fields"].items() if v is not None}
        shot = client.post(
            "/api/shots",
            json={
                **fields,
                "maker": "Scott",
                "coffee_id": coffee["id"],
                "notes": body["notes"],
            },
        ).get_json()

        telemetry_bytes = json.dumps(body["telemetry"]).encode()
        upload = client.post(
            f"/api/shots/{shot['id']}/telemetry",
            data={"file": (io.BytesIO(telemetry_bytes), body["telemetry_filename"])},
            content_type="multipart/form-data",
        )

        assert upload.status_code == 200
        saved = upload.get_json()
        telemetry_dir = tmp_path / "telemetry"
        stored = json.loads((telemetry_dir / saved["telemetry_filename"]).read_text())
        assert stored["metadata"]["shot"]["name"] == "My shot #19"
        thumbnail = telemetry_dir / saved["telemetry_thumbnail_filename"]
        assert thumbnail.read_bytes().startswith(b"\x89PNG")
    finally:
        config.uploads.coffee_image_dir = previous_dir
