#!/usr/bin/env python3
"""Visualize and edit Beanconqueror telemetry JSON files.

Usage examples:
  # Visualize only (saves <input>_edited.json)
  python bin/edit_telemetry.py data.json

  # Trim window and smooth, rename with shot ID
  python bin/edit_telemetry.py data.json \\
      --start-time 2.0 --end-time 28.0 \\
      --weight 5 --flow 3 \\
      --shot-id 1234
"""

import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

# All known top-level series keys in a Beanconqueror flow profile
ALL_SERIES_KEYS = [
    "weight",
    "weightSecond",
    "waterFlow",
    "realtimeFlow",
    "realtimeFlowSecond",
    "pressureFlow",
    "temperatureFlow",
    "brewbyweight",
]

# (series_key, value_field, y-axis label, color)
PLOT_CONFIG: list[tuple[str, str, str, str]] = [
    ("weight", "actual_weight", "Weight (g)", "tab:blue"),
    ("realtimeFlow", "flow_value", "Flow (g/s)", "tab:orange"),
    ("pressureFlow", "actual_pressure", "Pressure (bar)", "tab:red"),
    ("waterFlow", "value", "Water Flow (ml/s)", "tab:green"),
]

# brew_time fields that should never be clamped (not sensor measurements)
_BREW_TIME_KEYS = {"brew_time", "timestamp"}


def get_brew_time(item: dict[str, Any]) -> float:
    """Parse brew_time in Beanconqueror S.T format.

    The decimal part is tenths of a second (not a decimal fraction), so
    '0.10' means 1.0 s, not 0.1 s. float() gives the wrong answer for
    any value with two or more digits after the dot.
    """
    s = str(item["brew_time"])
    if "." in s:
        int_part, frac_part = s.split(".", 1)
        return int(int_part) + int(frac_part) / 10.0
    return float(s)


def set_brew_time(item: dict[str, Any], value: float) -> None:
    """Write brew_time preserving the original format style.

    Items whose brew_time had no '.' (e.g. waterFlow uses '0','1',...) keep
    that integer-string format. All others use 'S.T' (tenths digit 0-9).
    """
    total_tenths = round(value * 10)
    seconds = total_tenths // 10
    tenths = total_tenths % 10
    original = str(item["brew_time"])
    if "." in original:
        item["brew_time"] = f"{seconds}.{tenths}"
    else:
        item["brew_time"] = str(seconds)


def trim_series(
    series: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    """Filter series to [start, end] and renumber brew_time from zero."""
    filtered = [item for item in series if start <= get_brew_time(item) <= end]
    for item in filtered:
        set_brew_time(item, get_brew_time(item) - start)
    return filtered


def boxcar_smooth(values: list[float], window: int) -> list[float]:
    """Replace interior values with a centered boxcar average; leave edges unchanged."""
    half = window // 2
    result = values.copy()
    for i in range(half, len(values) - half):
        result[i] = sum(values[i - half : i + half + 1]) / window
    return result


def apply_smooth(series: list[dict[str, Any]], field: str, window: int) -> None:
    """Smooth a named numeric field in the series in-place."""
    values = [float(str(item[field])) for item in series]
    smoothed = boxcar_smooth(values, window)
    for item, v in zip(series, smoothed):
        item[field] = v


def clamp_all_fields(series: list[dict[str, Any]]) -> None:
    """Replace any negative numeric value in every field (except brew_time/timestamp) with 0."""
    for item in series:
        for key, val in item.items():
            if key not in _BREW_TIME_KEYS and isinstance(val, (int, float)) and val < 0:
                item[key] = 0


def plot_data(
    data: dict[str, list[dict[str, Any]]],
    title: str,
) -> None:
    """Display a stacked chart of all non-empty plottable series."""
    active = [
        (key, field, label, color)
        for key, field, label, color in PLOT_CONFIG
        if data.get(key)
    ]
    if not active:
        logger.warning("No plottable series found in data")
        return

    fig, axes = plt.subplots(
        len(active), 1, figsize=(12, 3 * len(active)), sharex=True
    )
    ax_list: list[Any] = [axes] if len(active) == 1 else list(axes)

    fig.suptitle(title, fontsize=12)

    for ax, (key, field, label, color) in zip(ax_list, active):
        series = data[key]
        times = [get_brew_time(item) for item in series]
        values = [float(str(item[field])) for item in series]
        ax.plot(times, values, color=color, linewidth=1.5)
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)

    ax_list[-1].set_xlabel("Brew Time (s)")
    plt.tight_layout()
    plt.show()


def parse_shot_datetime(path: Path) -> datetime | None:
    """Parse shot datetime from a Beanconqueror filename.

    Expected suffix: _HH_MM_SS_DD_MM_YYYY.json
    """
    m = re.search(
        r"_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{4})\.json$",
        path.name,
    )
    if not m:
        return None
    hh, mm, ss, dd, mon, yyyy = m.groups()
    return datetime(int(yyyy), int(mon), int(dd), int(hh), int(mm), int(ss))


def make_output_path(input_path: Path, shot_id: int | None) -> Path:
    """Return output file path based on shot ID and parsed filename datetime."""
    if shot_id is not None:
        dt = parse_shot_datetime(input_path)
        if dt:
            name = f"shot_{shot_id}_{dt.strftime('%Y-%m-%d_%H%M%S')}.json"
        else:
            logger.warning(
                "Could not parse datetime from filename; using shot ID only"
            )
            name = f"shot_{shot_id}.json"
        return input_path.parent / name
    return input_path.parent / f"{input_path.stem}_edited.json"


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Beanconqueror flow-profile JSON file",
    )
    parser.add_argument(
        "--start-time",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Trim: keep brew_time >= this value (seconds)",
    )
    parser.add_argument(
        "--end-time",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Trim: keep brew_time <= this value (seconds)",
    )
    parser.add_argument(
        "--weight",
        type=int,
        choices=[3, 5],
        default=None,
        metavar="{3,5}",
        help="Boxcar smooth actual_weight with window of N points",
    )
    parser.add_argument(
        "--flow",
        type=int,
        choices=[3, 5],
        default=None,
        metavar="{3,5}",
        help="Boxcar smooth flow_value (realtimeFlow) with window of N points",
    )
    parser.add_argument(
        "--pressure",
        type=int,
        choices=[3, 5],
        default=None,
        metavar="{3,5}",
        help="Boxcar smooth actual_pressure with window of N points",
    )
    parser.add_argument(
        "--shot-id",
        type=int,
        default=None,
        metavar="INT",
        help="Database shot ID — used to name the output file",
    )
    return parser


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    input_path: Path = args.input_file
    data: dict[str, list[dict[str, Any]]] = json.loads(input_path.read_text())

    # Sort all series by brew_time (Beanconqueror writes them in order but the
    # S.T format means float() comparisons are unreliable; sort defensively).
    for key in ALL_SERIES_KEYS:
        if data.get(key):
            data[key].sort(key=get_brew_time)

    # Step 1: show initial chart
    plot_data(data, f"Initial: {input_path.name}")

    edited = False

    # Step 2: trim
    if args.start_time is not None or args.end_time is not None:
        all_times: list[float] = []
        for key in ALL_SERIES_KEYS:
            if data.get(key):
                all_times.extend(get_brew_time(item) for item in data[key])

        start: float = args.start_time if args.start_time is not None else min(all_times)
        end: float = args.end_time if args.end_time is not None else max(all_times)

        for key in ALL_SERIES_KEYS:
            if data.get(key):
                data[key] = trim_series(data[key], start, end)

        logger.info(
            "Trimmed to brew_time [%.2f, %.2f] and renumbered from 0", start, end
        )
        edited = True

    # Step 3: smooth
    smooth_targets: list[tuple[int | None, str, str]] = [
        (args.weight, "weight", "actual_weight"),
        (args.flow, "realtimeFlow", "flow_value"),
        (args.pressure, "pressureFlow", "actual_pressure"),
    ]
    for window, key, field in smooth_targets:
        if window is not None and data.get(key):
            apply_smooth(data[key], field, window)
            logger.info("Smoothed %s.%s with window=%d", key, field, window)
            edited = True

    # Step 4: clamp all negative numeric values to zero across every series
    for key in ALL_SERIES_KEYS:
        if data.get(key):
            clamp_all_fields(data[key])

    # Step 5: save
    out_path = make_output_path(input_path, args.shot_id)
    out_path.write_text(json.dumps(data, indent=2))
    print(str(out_path))

    # Step 6: post-edit chart
    if edited:
        plot_data(data, f"Edited: {out_path.name}")


if __name__ == "__main__":
    main()
