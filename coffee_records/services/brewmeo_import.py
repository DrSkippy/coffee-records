"""Import a Brewmeo shot CSV export into shot form values and telemetry JSON.

A Brewmeo CSV has ``meta`` rows (``metatype`` label -> ``metadata`` value, with
the unit or type in ``comment``) followed by ``moment`` rows holding timestamped
weight, pressure and temperature samples. Nothing here writes to the database or
disk: callers get form prefill values, a proposed new coffee when needed, a
notes block for unmatched metadata, and Beanconqueror-compatible telemetry.
"""

import csv
import io
import json
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from coffee_records.config import BrewmeoConfig, MatchingConfig
from coffee_records.models.coffee import Coffee, RoastLevel
from coffee_records.models.equipment import BrewingDevice, Grinder
from coffee_records.schemas.coffee import CoffeeCreate
from coffee_records.schemas.shot import ShotCsvImportFields, ShotCsvImportResponse
from coffee_records.services.matching import best_equipment_match, is_same_beans
from coffee_records.services.telemetry import (
    TelemetryValidationError,
    extract_thumbnail_series,
)

REQUIRED_COLUMNS = frozenset(
    {
        "information_type",
        "elapsed",
        "pressure",
        "current_total_shot_weight",
        "metatype",
        "metadata",
        "comment",
    }
)
_TEMPERATURE_COLUMNS = (
    "water_temperature_in",
    "water_temperature_basket",
    "water_temperature_boiler",
)

# Labels mapped to shot/coffee fields (never repeated in notes).
_SHOT_LABELS = frozenset(
    {
        "Name",
        "Weight",
        "Dose",
        "Date",
        "Extraction time",
        "Grinder Setting",
        "Preinfusion Time",
        "Operator",
    }
)
_COFFEE_LABELS = frozenset(
    {"Beans", "Roastery", "Roasting Date", "Roast Color", "Variety"}
)
_GRINDER_LABELS = ("Grinder Brand", "Grinder Name", "Grinder Model")
_MACHINE_LABELS = (
    "Espresso Machine Brand",
    "Espresso Machine Name",
    "Espresso Machine Model",
)
# Export boilerplate kept only in the telemetry metadata.
_BOILERPLATE_LABELS = frozenset(
    {"Unit system", "Attribution", "Software", "Url", "Export version"}
)
_LABEL_DISPLAY = {"Avarage flow rate": "Average flow rate"}
_UNIT_DISPLAY = {
    "celsius": "°C",
    "sec": "s",
    "g/sec": "g/s",
    "weight in kg": "kg",
    "grounds weight in g": "g",
    "number in range 1 .. 10": "/10",
}

# Flow is derived on a fixed 0.1 s grid (Beanconqueror's brew_time resolution).
_GRID_STEPS_PER_SECOND = 10
_GRID_STEP_MS = 1000 // _GRID_STEPS_PER_SECOND
# Clock origin for telemetry timestamps when the CSV carries no shot date.
_FALLBACK_START = datetime(2000, 1, 1)


class BrewmeoImportError(ValueError):
    """Raised when an uploaded file is not a usable Brewmeo shot CSV."""


Sample = tuple[float, float]


@dataclass
class BrewmeoShot:
    """Parsed contents of a Brewmeo CSV."""

    meta: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    weight: list[Sample] = field(default_factory=list)
    pressure: list[Sample] = field(default_factory=list)
    temperature: list[Sample] = field(default_factory=list)

    def text(self, label: str) -> str | None:
        """Return the stripped meta value, or None when missing or empty."""
        value = self.meta.get(label, "").strip()
        return value or None

    def positive(self, label: str) -> float | None:
        """Return the meta value as a finite float > 0, else None."""
        value = _to_float(self.text(label))
        return value if value is not None and value > 0 else None

    def when(self, label: str) -> datetime | None:
        """Return the meta value parsed as an ISO 8601 datetime, else None."""
        value = self.text(label)
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _to_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def parse_brewmeo_csv(text: str) -> BrewmeoShot:
    """Parse a Brewmeo CSV export.

    Args:
        text: Decoded CSV contents.

    Returns:
        The parsed metadata and samples, each series sorted by elapsed time.

    Raises:
        BrewmeoImportError: If required columns or metadata rows are missing.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise BrewmeoImportError(
            "Not a Brewmeo shot CSV (missing columns: "
            + ", ".join(sorted(missing))
            + ")"
        )

    shot = BrewmeoShot()
    for row in reader:
        kind = (row.get("information_type") or "").strip()
        if kind == "meta":
            label = (row.get("metatype") or "").strip()
            if label:
                shot.meta[label] = (row.get("metadata") or "").strip()
                shot.units[label] = (row.get("comment") or "").strip()
        elif kind == "moment":
            elapsed = _to_float(row.get("elapsed"))
            if elapsed is None or elapsed < 0:
                continue
            weight = _to_float(row.get("current_total_shot_weight"))
            if weight is not None:
                shot.weight.append((elapsed, weight))
            pressure = _to_float(row.get("pressure"))
            if pressure is not None:
                shot.pressure.append((elapsed, pressure))
            for column in _TEMPERATURE_COLUMNS:
                temperature = _to_float(row.get(column))
                if temperature is not None:
                    shot.temperature.append((elapsed, temperature))
                    break

    if not shot.meta:
        raise BrewmeoImportError("CSV contains no shot metadata rows")
    for series in (shot.weight, shot.pressure, shot.temperature):
        series.sort(key=lambda sample: sample[0])
    return shot


def format_brew_time(elapsed: float) -> str:
    """Format seconds as Beanconqueror ``S.T`` brew time (T = tenths).

    Args:
        elapsed: Seconds since the start of the shot.

    Returns:
        E.g. ``37.908`` -> ``"37.9"``, ``0.96`` -> ``"1.0"``.
    """
    tenths = round(elapsed * 10)
    return f"{tenths // 10}.{tenths % 10}"


def _clock(start: datetime, elapsed: float) -> str:
    return (start + timedelta(seconds=elapsed)).strftime("%H:%M:%S.%f")[:-3]


def trim_weight_disturbance(
    weight: list[Sample], settings: BrewmeoConfig | None = None
) -> tuple[list[Sample], float | None]:
    """Drop a scale disturbance at the end of the weight trace.

    Looks for the first jump of more than ``disturbance_grams`` within
    ``disturbance_seconds`` in the last ``disturbance_tail_fraction`` of the
    shot (e.g. the cup lifted or bumped as the shot ends) and removes that
    sample and everything after it. Earlier samples are never touched.

    Args:
        weight: ``(elapsed_s, grams)`` samples sorted by time.
        settings: Disturbance thresholds (defaults to built-in settings).

    Returns:
        The kept samples and the elapsed time where trimming began, or the
        original samples and None when no disturbance was found.
    """
    settings = settings or BrewmeoConfig()
    if len(weight) < 2:
        return weight, None
    tail_start = weight[-1][0] * (1 - settings.disturbance_tail_fraction)
    for i in range(1, len(weight)):
        (t0, w0), (t1, w1) = weight[i - 1], weight[i]
        if (
            t1 >= tail_start
            and abs(w1 - w0) > settings.disturbance_grams
            and t1 - t0 <= settings.disturbance_seconds
        ):
            return weight[:i], t1
    return weight, None


def derive_flow(
    weight: list[Sample], settings: BrewmeoConfig | None = None
) -> list[tuple[float, float, float]]:
    """Derive a flow-rate series (g/s) from weight samples.

    Weight is interpolated onto a 0.1 s grid, smoothed with a centered moving
    average, then differentiated over a centered 1 s window. Negative flow
    (scale noise, cup adjustments) is clamped to zero.

    Args:
        weight: ``(elapsed_s, grams)`` samples sorted by time.
        settings: Smoothing windows (defaults to built-in settings).

    Returns:
        ``(elapsed_s, smoothed_grams, flow_g_per_s)`` per 0.1 s step.
    """
    settings = settings or BrewmeoConfig()
    if len(weight) < 2:
        return []
    times = np.array([t for t, _ in weight])
    grams = np.array([w for _, w in weight])
    steps = round(float(times[-1]) * _GRID_STEPS_PER_SECOND)
    grid = np.arange(0, steps + 1) / _GRID_STEPS_PER_SECOND
    if len(grid) < 2:
        return []
    resampled = np.interp(grid, times, grams)
    window = settings.flow_smoothing_tenths
    kernel = np.ones(window) / window
    smoothed = np.convolve(np.pad(resampled, window // 2, mode="edge"), kernel, "valid")

    half_window = settings.flow_half_window_tenths
    last = len(grid) - 1
    result: list[tuple[float, float, float]] = []
    for i, t in enumerate(grid):
        lo = max(i - half_window, 0)
        hi = min(i + half_window, last)
        flow = (smoothed[hi] - smoothed[lo]) / (grid[hi] - grid[lo])
        result.append((float(t), float(smoothed[i]), max(float(flow), 0.0)))
    return result


def _with_previous(samples: list[Sample]) -> Iterator[tuple[float, float, float]]:
    """Yield ``(elapsed, value, previous_value)``, with 0.0 before the first sample.

    Args:
        samples: ``(elapsed_s, value)`` samples sorted by time.

    Yields:
        Each sample alongside the preceding sample's value.
    """
    previous = 0.0
    for elapsed, value in samples:
        yield elapsed, value, previous
        previous = value


def _time_fields(start: datetime, elapsed: float) -> dict[str, str]:
    """Return Beanconqueror's ``timestamp`` and ``brew_time`` fields.

    Args:
        start: Wall-clock time of the shot start.
        elapsed: Seconds since the start of the shot.

    Returns:
        The two timing fields for one telemetry entry.
    """
    return {"timestamp": _clock(start, elapsed), "brew_time": format_brew_time(elapsed)}


def to_telemetry_json(
    shot: BrewmeoShot, source_file: str, settings: BrewmeoConfig | None = None
) -> dict[str, Any]:
    """Convert parsed samples to Beanconqueror flow-profile JSON plus metadata.

    Args:
        shot: Parsed CSV.
        source_file: Original upload filename, recorded in the metadata.
        settings: Signal-processing settings (defaults to built-in settings).

    Returns:
        A JSON-serializable dict with the Beanconqueror series keys and a
        ``metadata`` object describing the shot and its source.
    """
    shot_date = shot.when("Date")
    start = shot_date or _FALLBACK_START
    weight, trimmed_from = trim_weight_disturbance(shot.weight, settings)

    weight_entries = [
        {
            **_time_fields(start, elapsed),
            "actual_weight": grams,
            "old_weight": previous,
            "actual_smoothed_weight": grams,
            "old_smoothed_weight": previous,
            "not_mutated_weight": grams,
        }
        for elapsed, grams, previous in _with_previous(weight)
    ]
    pressure_entries = [
        {**_time_fields(start, elapsed), "actual_pressure": bar, "old_pressure": prev}
        for elapsed, bar, prev in _with_previous(shot.pressure)
    ]
    temperature_entries = [
        {
            **_time_fields(start, elapsed),
            "actual_temperature": celsius,
            "old_temperature": previous,
        }
        for elapsed, celsius, previous in _with_previous(shot.temperature)
    ]
    flow_entries = [
        {
            **_time_fields(start, elapsed),
            "smoothed_weight": round(smoothed, 3),
            "timestampdelta": _GRID_STEP_MS,
            "flow_value": round(flow, 3),
        }
        for elapsed, smoothed, flow in derive_flow(weight, settings)
    ]

    return {
        "weight": weight_entries,
        "weightSecond": [],
        "waterFlow": [],
        "realtimeFlow": flow_entries,
        "realtimeFlowSecond": [],
        "pressureFlow": pressure_entries,
        "temperatureFlow": temperature_entries,
        "brewbyweight": [],
        "metadata": {
            "source": shot.text("Software") or "Brewmeo",
            "source_file": source_file,
            "export_version": shot.text("Export version"),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "flow_derived_from_weight": True,
            "weight_trimmed_from": trimmed_from,
            "weight_samples_trimmed": len(shot.weight) - len(weight),
            "shot": {
                "name": shot.text("Name"),
                "date": shot_date.isoformat() if shot_date else None,
                "final_weight": shot.positive("Weight"),
                "dose": shot.positive("Dose"),
                "extraction_time": shot.positive("Extraction time"),
                "grind_setting": shot.text("Grinder Setting"),
                "average_flow_rate": shot.positive("Avarage flow rate"),
                "beans": shot.text("Beans"),
                "roastery": shot.text("Roastery"),
                "grinder": shot.text("Grinder Name"),
                "machine": shot.text("Espresso Machine Name"),
            },
            "meta": {label: value for label, value in shot.meta.items() if value},
        },
    }


def _format_value(value: str) -> str:
    number = _to_float(value)
    if number is None:
        return value
    return f"{number:.2f}".rstrip("0").rstrip(".")


def compose_notes(shot: BrewmeoShot, consumed: set[str]) -> str:
    """Build a plain-text notes block from metadata not mapped to a field.

    Skips consumed labels, ``... Id`` UUIDs, export boilerplate, empty values
    and zeros. Brew ratio is skipped when no dose was recorded, since it is
    meaningless without one.

    Args:
        shot: Parsed CSV.
        consumed: Labels already mapped to shot or coffee fields.

    Returns:
        Notes text headed by the Brewmeo shot name.
    """
    lines = [f"Imported from Brewmeo: {shot.text('Name') or 'shot'}"]
    for label, value in shot.meta.items():
        if (
            label in consumed
            or label in _BOILERPLATE_LABELS
            or label.endswith(" Id")
            or not value
            or _to_float(value) == 0
        ):
            continue
        if label == "Brew ratio" and shot.positive("Dose") is None:
            continue
        unit = _UNIT_DISPLAY.get(shot.units.get(label, ""), "")
        display = _LABEL_DISPLAY.get(label, label)
        text = _format_value(value)
        suffix = "" if not unit else (unit if unit == "/10" else f" {unit}")
        lines.append(f"{display}: {text}{suffix}")
    return "\n".join(lines)


def _roast_level(text: str | None) -> RoastLevel | None:
    """Map a Brewmeo roast color to a RoastLevel.

    Args:
        text: Roast color label, any case.

    Returns:
        The matching RoastLevel, or None if unrecognised.
    """
    try:
        return RoastLevel((text or "").lower())
    except ValueError:
        return None


def _match_coffee(
    session: Session, shot: BrewmeoShot, matching: MatchingConfig | None = None
) -> tuple[int | None, CoffeeCreate | None, list[str]]:
    """Match the CSV beans to a coffee, or propose a new one.

    A match requires fuzzy name and roaster agreement plus the same roast
    date. A name/roaster match with a different roast date is treated as a
    new bag; its origin and process are carried over to the proposal.

    Args:
        session: Read-only database session.
        shot: Parsed CSV.
        matching: Fuzzy-match thresholds.

    Returns:
        ``(existing coffee id, proposed new coffee, warnings)``.
    """
    name = shot.text("Beans")
    roaster = shot.text("Roastery")
    if not name:
        return None, None, ["CSV has no beans name; coffee left unchanged"]
    roasted = shot.when("Roasting Date")
    roast_date: date | None = roasted.date() if roasted else None

    same_beans = [
        c
        for c in session.query(Coffee).all()
        if is_same_beans(name, roaster, c.name or "", c.roaster or "", matching)
    ]
    if roast_date is not None:
        exact = [c for c in same_beans if c.roast_date == roast_date]
    else:
        exact = sorted(same_beans, key=lambda c: c.roast_date or date.min)[-1:]
    if exact:
        return exact[0].id, None, []

    previous_bag = max(same_beans, key=lambda c: c.roast_date or date.min, default=None)
    proposal = CoffeeCreate(
        name=name,
        roaster=roaster or "Unknown",
        roast_date=roast_date,
        roast_level=_roast_level(shot.text("Roast Color")),
        variety=shot.text("Variety"),
        origin_country=previous_bag.origin_country if previous_bag else None,
        process=previous_bag.process if previous_bag else None,
    )
    return None, proposal, []


def _equipment_label(shot: BrewmeoShot, labels: tuple[str, ...]) -> str:
    """Join brand, name and model, skipping parts the name already contains."""
    brand, name, model = (shot.text(label) or "" for label in labels)
    parts = [
        brand if brand.lower() not in name.lower() else "",
        name,
        model if model.lower() not in name.lower() else "",
    ]
    return " ".join(part for part in parts if part)


def _safe_filename(name: str | None) -> str:
    slug = re.sub(r"[^0-9a-z]+", "-", (name or "").lower()).strip("-")
    return f"{slug or 'brewmeo-shot'}.json"


def build_import(
    session: Session,
    shot: BrewmeoShot,
    source_file: str,
    brewmeo: BrewmeoConfig | None = None,
    matching: MatchingConfig | None = None,
) -> ShotCsvImportResponse:
    """Map a parsed CSV onto shot form values, coffee, equipment and notes.

    Args:
        session: Read-only database session used for matching.
        shot: Parsed CSV.
        source_file: Original upload filename.
        brewmeo: Signal-processing settings (defaults to built-in settings).
        matching: Fuzzy-match thresholds (defaults to built-in settings).

    Returns:
        The import response; nothing is written to the database.
    """
    brewmeo = brewmeo or BrewmeoConfig()
    matching = matching or MatchingConfig()
    warnings: list[str] = []
    consumed = set(_SHOT_LABELS | _COFFEE_LABELS)

    coffee_id, new_coffee, coffee_warnings = _match_coffee(session, shot, matching)
    warnings.extend(coffee_warnings)

    grinder_label = _equipment_label(shot, _GRINDER_LABELS)
    grinder_id = best_equipment_match(
        grinder_label,
        ((g.id, f"{g.make} {g.model}") for g in session.query(Grinder).all()),
        min_overlap=matching.equipment_min_overlap,
    )
    if grinder_id is not None:
        consumed.update(_GRINDER_LABELS)
    elif grinder_label:
        warnings.append(f"Grinder '{grinder_label}' not found; left unselected")

    machine_label = _equipment_label(shot, _MACHINE_LABELS)
    device_id = best_equipment_match(
        machine_label,
        ((d.id, f"{d.make} {d.model}") for d in session.query(BrewingDevice).all()),
        min_overlap=matching.equipment_min_overlap,
    )
    if device_id is not None:
        consumed.update(_MACHINE_LABELS)
    elif machine_label:
        warnings.append(f"Machine '{machine_label}' not found; left unselected")

    final_weight = shot.positive("Weight")
    kept, trimmed_from = trim_weight_disturbance(shot.weight, brewmeo)
    if trimmed_from is not None:
        warnings.append(
            f"Scale disturbance at {trimmed_from:.1f} s removed from the weight trace"
        )
    if kept and final_weight is not None:
        trace_final = kept[-1][1]
        if abs(final_weight - trace_final) > brewmeo.final_weight_tolerance_grams:
            warnings.append(
                f"CSV final weight {final_weight:.1f} g disagrees with the scale "
                f"trace ({trace_final:.1f} g at the end of the shot); check Final Weight"
            )

    extraction = shot.positive("Extraction time")
    shot_date = shot.when("Date")
    fields = ShotCsvImportFields(
        date=shot_date.date() if shot_date else None,
        recorded_at=shot_date,
        maker=shot.text("Operator"),
        coffee_id=coffee_id,
        dose_weight=shot.positive("Dose"),
        pre_infusion_time=shot.text("Preinfusion Time"),
        extraction_time=round(extraction, 1) if extraction is not None else None,
        final_weight=final_weight,
        grind_setting=shot.text("Grinder Setting"),
        grinder_id=grinder_id,
        device_id=device_id,
    )

    telemetry: dict[str, Any] | None = to_telemetry_json(shot, source_file, brewmeo)
    try:
        extract_thumbnail_series(json.dumps(telemetry).encode())
    except TelemetryValidationError as exc:
        warnings.append(f"No telemetry attached: {exc}")
        telemetry = None

    return ShotCsvImportResponse(
        source=source_file,
        fields=fields,
        new_coffee=new_coffee,
        notes=compose_notes(shot, consumed),
        telemetry=telemetry,
        telemetry_filename=_safe_filename(shot.text("Name")) if telemetry else None,
        warnings=warnings,
    )
