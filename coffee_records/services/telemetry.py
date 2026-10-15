"""Parse Beanconqueror telemetry and render compact chart thumbnails."""

import io
import json
import math
from collections.abc import Mapping
from typing import Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from coffee_records.services import brew_time

# Thumbnail geometry: 320x106 px at 100 dpi.
_THUMBNAIL_SIZE_IN = (3.2, 1.06)
_THUMBNAIL_DPI = 100
_LINE_WIDTH = 1.5
_SERIES_COLORS = {"weight": "#228be6", "flow": "#12b886", "pressure": "#fd7e14"}
_GRID_COLOR = "#ced4da"


class TelemetryValidationError(ValueError):
    """Raised when uploaded telemetry cannot produce a useful chart."""


Series = list[tuple[float, float]]


def parse_brew_time(value: object) -> float:
    """Parse Beanconqueror's ``S.T`` brew-time representation.

    Args:
        value: Raw brew_time value.

    Returns:
        Elapsed seconds.

    Raises:
        TelemetryValidationError: If the value is malformed or not finite.
    """
    try:
        return brew_time.parse_brew_time(value)
    except ValueError as exc:
        raise TelemetryValidationError(f"Invalid brew_time: {value}") from exc


def _number(entry: Mapping[str, Any], fields: tuple[str, ...]) -> float | None:
    """Return the first finite numeric field of an entry.

    Args:
        entry: Telemetry sample.
        fields: Candidate field names, in priority order.

    Returns:
        The value, or None when no field holds a finite number.
    """
    for field in fields:
        value = entry.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
            if math.isfinite(result):
                return result
    return None


def _series(raw: Mapping[str, Any], key: str, value_fields: tuple[str, ...]) -> Series:
    """Extract ``(seconds, value)`` points from one telemetry series.

    Samples without a usable time or value are skipped by design: real
    exports contain sparse or partially-filled entries.

    Args:
        raw: Parsed telemetry JSON.
        key: Series key (e.g. "weight").
        value_fields: Candidate value fields, in priority order.

    Returns:
        Points sorted by time.

    Raises:
        TelemetryValidationError: If the series is present but not an array.
    """
    entries = raw.get(key, [])
    if not isinstance(entries, list):
        raise TelemetryValidationError(f"Telemetry series '{key}' must be an array")
    points: Series = []
    for item in entries:
        if not isinstance(item, Mapping) or "brew_time" not in item:
            continue
        value = _number(item, value_fields)
        if value is None:
            continue
        try:
            points.append((parse_brew_time(item["brew_time"]), value))
        except TelemetryValidationError:
            continue
    points.sort(key=lambda point: point[0])
    return points


def extract_thumbnail_series(payload: bytes) -> dict[str, Series]:
    """Validate JSON and return its non-empty, non-zero chart series.

    Args:
        payload: Raw telemetry file contents.

    Returns:
        Series name ("weight", "flow", "pressure") to points.

    Raises:
        TelemetryValidationError: If the JSON is invalid or has no usable data.
    """
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryValidationError("Telemetry must be valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise TelemetryValidationError("Telemetry JSON must contain an object")

    candidates = {
        "weight": _series(raw, "weight", ("actual_smoothed_weight", "actual_weight")),
        "flow": _series(raw, "realtimeFlow", ("flow_value",)),
        "pressure": _series(raw, "pressureFlow", ("actual_pressure",)),
    }
    active = {
        name: points
        for name, points in candidates.items()
        if points and any(value != 0 for _, value in points)
    }
    if not active:
        raise TelemetryValidationError("Telemetry contains no usable chart data")
    return active


def _hide_frame(axis: Axes) -> None:
    """Remove ticks, tick labels and spines from an axis.

    Args:
        axis: Axis to strip.
    """
    axis.tick_params(
        left=False,
        right=False,
        bottom=False,
        labelleft=False,
        labelright=False,
        labelbottom=False,
    )
    for spine in axis.spines.values():
        spine.set_visible(False)


def render_telemetry_thumbnail(payload: bytes) -> bytes:
    """Render telemetry JSON to a 320x106 PNG thumbnail.

    Flow and pressure share the left axis; weight (when present) uses its
    own right axis. Uses the object-oriented Figure API, so no global pyplot
    state is touched and nothing needs closing.

    Args:
        payload: Raw telemetry file contents.

    Returns:
        PNG bytes with a transparent background.

    Raises:
        TelemetryValidationError: If the telemetry has no usable chart data.
    """
    series = extract_thumbnail_series(payload)
    figure = Figure(figsize=_THUMBNAIL_SIZE_IN, dpi=_THUMBNAIL_DPI)
    left_axis = figure.add_subplot()
    right_axis = left_axis.twinx() if "weight" in series else None

    for name in ("flow", "pressure"):
        if name in series:
            times, values = zip(*series[name])
            left_axis.plot(
                times, values, color=_SERIES_COLORS[name], linewidth=_LINE_WIDTH
            )
    if right_axis is not None:
        times, values = zip(*series["weight"])
        right_axis.plot(
            times, values, color=_SERIES_COLORS["weight"], linewidth=_LINE_WIDTH
        )
        right_axis.set_ylim(bottom=0)
        _hide_frame(right_axis)

    left_axis.set_ylim(bottom=0)
    left_axis.grid(color=_GRID_COLOR, alpha=0.45, linewidth=0.5)
    _hide_frame(left_axis)
    figure.patch.set_alpha(0)
    left_axis.set_facecolor("none")
    figure.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.03)

    output = io.BytesIO()
    figure.savefig(output, format="png", transparent=True, dpi=_THUMBNAIL_DPI)
    return output.getvalue()
