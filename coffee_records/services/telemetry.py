"""Parse Beanconqueror telemetry and render compact chart thumbnails."""

import io
import json
import math
from collections.abc import Mapping
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


class TelemetryValidationError(ValueError):
    """Raised when uploaded telemetry cannot produce a useful chart."""


Series = list[tuple[float, float]]


def parse_brew_time(value: object) -> float:
    """Parse Beanconqueror's ``S.T`` brew-time representation."""
    text = str(value)
    try:
        if "." not in text:
            result = float(text)
        else:
            seconds, tenths = text.split(".", 1)
            result = int(seconds) + int(tenths) / 10
    except (TypeError, ValueError) as exc:
        raise TelemetryValidationError(f"Invalid brew_time: {text}") from exc
    if not math.isfinite(result):
        raise TelemetryValidationError(f"Invalid brew_time: {text}")
    return result


def _number(entry: Mapping[str, Any], fields: tuple[str, ...]) -> float | None:
    for field in fields:
        value = entry.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
            if math.isfinite(result):
                return result
    return None


def _series(raw: Mapping[str, Any], key: str, value_fields: tuple[str, ...]) -> Series:
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
    """Validate JSON and return its non-empty, non-zero chart series."""
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


def render_telemetry_thumbnail(payload: bytes) -> bytes:
    """Render telemetry JSON to a 320x106 PNG thumbnail."""
    series = extract_thumbnail_series(payload)
    figure, left_axis = plt.subplots(figsize=(3.2, 1.06), dpi=100)
    right_axis = left_axis.twinx() if "weight" in series else None
    colors = {"weight": "#228be6", "flow": "#12b886", "pressure": "#fd7e14"}

    for name in ("flow", "pressure"):
        if name in series:
            times, values = zip(*series[name])
            left_axis.plot(times, values, color=colors[name], linewidth=1.5)
    if right_axis is not None:
        times, values = zip(*series["weight"])
        right_axis.plot(times, values, color=colors["weight"], linewidth=1.5)

    left_axis.set_ylim(bottom=0)
    if right_axis is not None:
        right_axis.set_ylim(bottom=0)
        right_axis.tick_params(
            left=False, right=False, labelleft=False, labelright=False
        )
        for spine in right_axis.spines.values():
            spine.set_visible(False)
    left_axis.grid(color="#ced4da", alpha=0.45, linewidth=0.5)
    left_axis.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in left_axis.spines.values():
        spine.set_visible(False)
    figure.patch.set_alpha(0)
    left_axis.set_facecolor("none")
    figure.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.03)

    output = io.BytesIO()
    figure.savefig(output, format="png", transparent=True, dpi=100)
    plt.close(figure)
    return output.getvalue()
