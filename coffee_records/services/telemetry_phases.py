"""Estimate pre-infusion and shot time from shot telemetry by curve fitting.

Each phase boundary is the intersection of two ideal curve segments fitted
either side of a transition (see ``notebooks/telemetry_phases/README.md``):

* pump on: zero-pressure baseline ∩ rising pressure line;
* ramp: low pre-infusion plateau ∩ ramp to brew pressure (context only);
* flow on: flat weight baseline ∩ quadratic weight rise (start of stream);
* pump off: declining plateau line ∩ final pressure drop.

Recordings that auto-start already pressurised (Brewmeo) miss the pump-on
edge, so pump on is imputed a configured lead before the recording start.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from coffee_records.config import TelemetryPhasesConfig
from coffee_records.schemas.telemetry import PhaseIssue, TelemetryPhases
from coffee_records.services.telemetry import Series, extract_thumbnail_series

FloatArray = NDArray[np.float64]


@dataclass
class _Signal:
    """A time series sorted by time."""

    t: FloatArray
    y: FloatArray

    @classmethod
    def from_series(cls, points: Series, half_width: int) -> "_Signal":
        arr = np.array(points, dtype=np.float64).reshape(-1, 2)
        return cls(arr[:, 0], _median_filter(arr[:, 1], half_width))

    def window(self, start: float, end: float) -> "_Signal":
        mask = (self.t >= start) & (self.t <= end)
        return _Signal(self.t[mask], self.y[mask])

    def first_crossing(self, level: float, after: float = -math.inf) -> float | None:
        idx = np.nonzero((self.y >= level) & (self.t >= after))[0]
        return float(self.t[idx[0]]) if idx.size else None

    def last_above(self, level: float) -> float | None:
        idx = np.nonzero(self.y >= level)[0]
        return float(self.t[idx[-1]]) if idx.size else None


def _median_filter(y: FloatArray, half_width: int) -> FloatArray:
    """Running median; removes single-sample spikes (e.g. a bumped scale)."""
    if y.size == 0 or half_width <= 0:
        return y
    padded = np.pad(y, half_width, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half_width + 1)
    return np.asarray(np.median(windows, axis=1), dtype=np.float64)


def _design(t: FloatArray, t0: float, left_slope: bool, right_order: int) -> FloatArray:
    """Design matrix of a continuous two-segment curve with a knot at ``t0``."""
    hinge = np.maximum(t - t0, 0.0)
    columns = [np.ones_like(t)]
    if left_slope:
        columns.append(t)
    columns.extend(hinge**k for k in range(1, right_order + 1))
    return np.column_stack(columns)


def fit_breakpoint(
    t: FloatArray,
    y: FloatArray,
    step: float,
    left_slope: bool = False,
    right_order: int = 1,
    margin: float = 0.2,
) -> float | None:
    """Fit two continuous segments by least squares; return their intersection.

    Args:
        t: Sample times, sorted.
        y: Sample values.
        step: Breakpoint grid resolution (s).
        left_slope: Allow a sloped (not flat) left segment.
        right_order: Polynomial order of the right segment (1 = line).
        margin: Keep the breakpoint at least this far inside the window.

    Returns:
        The best breakpoint time, or None if the window is too small.
    """
    n_params = 1 + int(left_slope) + right_order
    if t.size < n_params + 3:
        return None
    lo, hi = float(t[0]) + margin, float(t[-1]) - margin
    if hi <= lo:
        return None
    best_t0, best_sse = None, math.inf
    for t0 in np.arange(lo, hi, step):
        design = _design(t, float(t0), left_slope, right_order)
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        sse = float(np.sum((design @ coef - y) ** 2))
        if sse < best_sse:
            best_t0, best_sse = float(t0), sse
    return best_t0


def _fit(
    signal: _Signal, step: float, left_slope: bool = False, right_order: int = 1
) -> float | None:
    return fit_breakpoint(signal.t, signal.y, step, left_slope, right_order)


def _pump_off(pressure: _Signal, settings: TelemetryPhasesConfig) -> float | None:
    """Final drop: declining plateau line ∩ steep drop line.

    Keyed on an absolute pressure, not a fraction of peak, so a flow-tapered
    shot (eased to ~1 bar before the pump stops) is cut at the real pump off.
    """
    t_drop = pressure.last_above(settings.pump_off_bar)
    if t_drop is None:
        return None
    tail = pressure.window(t_drop, math.inf)
    below = tail.t[tail.y <= settings.zero_pressure_bar]
    end = (
        float(below[0]) + settings.pump_off_tail_s if below.size else float(tail.t[-1])
    )
    window = pressure.window(t_drop - settings.plateau_lookback_s, end)
    return _fit(window, settings.grid_step_s, left_slope=True)


def _profile(
    pressure: _Signal,
    t_ramp: float,
    t_pump_off: float,
    peak: float,
    settings: TelemetryPhasesConfig,
) -> tuple[float, float, bool] | None:
    """Classify the brew plateau as a natural decline or a modulated profile.

    Returns:
        ``(end_ratio, rmse, profiled)``, or None if the plateau is too short.
    """
    t_peak = pressure.first_crossing(settings.peak_reach * peak, after=t_ramp)
    if t_peak is None:
        return None
    grid = np.arange(
        t_peak + settings.profile_start_margin_s,
        t_pump_off - settings.profile_end_margin_s,
        settings.profile_grid_step_s,
    )
    if grid.size < settings.profile_min_samples:
        return None
    y = np.interp(grid, pressure.t, pressure.y)
    end_ratio = float(np.median(y[-settings.profile_end_samples :])) / peak
    coef = np.polyfit(grid, y, 2)
    rmse = float(np.sqrt(np.mean((np.polyval(coef, grid) - y) ** 2)))
    profiled = (
        end_ratio < settings.profile_end_ratio or rmse > settings.profile_rmse_bar
    )
    return end_ratio, rmse, profiled


def estimate_phases(
    series: dict[str, Series], settings: TelemetryPhasesConfig | None = None
) -> TelemetryPhases:
    """Estimate shot phase boundaries from parsed telemetry series.

    Args:
        series: ``"pressure"`` and ``"weight"`` points, as returned by
            ``extract_thumbnail_series``.
        settings: Calibration (defaults to built-in settings).

    Returns:
        The fitted phases; missing values are explained in ``issues``.
    """
    settings = settings or TelemetryPhasesConfig()
    step = settings.grid_step_s
    result = TelemetryPhases()
    pressure_points = series.get("pressure", [])
    if len(pressure_points) < settings.min_pressure_samples:
        result.issues.append(PhaseIssue.no_pressure)
        return result
    pressure = _Signal.from_series(pressure_points, settings.median_half_width)
    weight = _Signal.from_series(series.get("weight", []), settings.median_half_width)

    start_bar = float(pressure.y[0])
    peak = float(np.percentile(pressure.y, settings.peak_percentile))
    result.recording_start_bar = round(start_bar, 2)
    result.peak_pressure_bar = round(peak, 2)
    if start_bar >= settings.truncated_start_bar:
        result.issues.append(PhaseIssue.truncated_start)
        return result

    # Pre-infusion plateau: median pressure (above zero) before the main ramp.
    ramp_reach_time = pressure.first_crossing(settings.ramp_reach * peak)
    early = pressure.window(-math.inf, ramp_reach_time or math.inf)
    early_y = early.y[early.y > settings.zero_pressure_bar]
    plateau = float(np.median(early_y)) if early_y.size else settings.plateau_floor_bar

    if start_bar < settings.zero_pressure_bar:
        reach = pressure.first_crossing(settings.pump_on_reach * plateau)
        if reach is not None:
            result.t_pump_on = _fit(pressure.window(-math.inf, reach), step)
    else:
        result.t_pump_on = float(pressure.t[0]) - settings.pump_on_offset_s
        result.pump_on_imputed = True
    if result.t_pump_on is None:
        result.issues.append(PhaseIssue.no_pump_on)
    origin = result.t_pump_on if result.t_pump_on is not None else float(pressure.t[0])

    ramp_end = pressure.first_crossing(
        settings.ramp_reach * peak, after=origin + settings.ramp_fit_start_s
    )
    if ramp_end is not None:
        result.t_ramp = _fit(
            pressure.window(origin + settings.ramp_fit_start_s, ramp_end),
            step,
            left_slope=True,
        )

    flow_end = weight.first_crossing(settings.flow_fit_max_g, after=origin)
    if flow_end is not None:
        result.t_flow_on = _fit(weight.window(origin, flow_end), step, right_order=2)
    if result.t_flow_on is None:
        result.issues.append(PhaseIssue.no_flow_on)

    result.t_pump_off = _pump_off(pressure, settings)
    if result.t_pump_off is None:
        result.issues.append(PhaseIssue.no_pump_off)

    if result.t_ramp is not None and result.t_pump_off is not None:
        profile = _profile(pressure, result.t_ramp, result.t_pump_off, peak, settings)
        if profile is not None:
            end_ratio, rmse, result.profiled = profile
            result.end_ratio = round(end_ratio, 3)
            result.plateau_rmse_bar = round(rmse, 3)

    if peak < settings.low_peak_bar:
        result.issues.append(PhaseIssue.low_peak_pressure)
    if (
        result.t_flow_on is not None
        and result.t_ramp is not None
        and result.t_flow_on < result.t_ramp - settings.flow_before_ramp_s
    ):
        result.issues.append(PhaseIssue.flow_before_ramp)

    if result.t_pump_on is not None and result.t_flow_on is not None:
        result.pre_infusion_s = round(result.t_flow_on - result.t_pump_on, 1)
    if result.t_flow_on is not None and result.t_pump_off is not None:
        result.shot_time_s = round(result.t_pump_off - result.t_flow_on, 1)
    for name in ("t_pump_on", "t_ramp", "t_flow_on", "t_pump_off"):
        value = getattr(result, name)
        if value is not None:
            setattr(result, name, round(value, 2))
    return result


def estimate_phases_from_payload(
    payload: bytes | Mapping[str, Any], settings: TelemetryPhasesConfig | None = None
) -> TelemetryPhases:
    """Estimate phases from raw telemetry JSON (or an already-parsed object).

    Args:
        payload: Telemetry file contents, or parsed telemetry JSON.
        settings: Calibration (defaults to built-in settings).

    Returns:
        The fitted phases.

    Raises:
        TelemetryValidationError: If the JSON is invalid or has no usable data.
    """
    return estimate_phases(extract_thumbnail_series(payload), settings)


def describe_phases(phases: TelemetryPhases) -> list[str]:
    """Render phase estimates as plain-text lines for shot notes.

    Args:
        phases: Estimated phases.

    Returns:
        Lines headed ``Telemetry estimates (curve fit):``.
    """
    lines = ["Telemetry estimates (curve fit):"]
    if PhaseIssue.no_pressure in phases.issues:
        lines.append("Pre-infusion and shot time: n/a (no pressure data)")
        return lines
    if PhaseIssue.truncated_start in phases.issues:
        lines.append(
            "Pre-infusion and shot time: n/a (recording started mid-shot at "
            f"{phases.recording_start_bar:.1f} bar)"
        )
        return lines

    if phases.pre_infusion_s is None:
        lines.append("Pre-infusion: n/a")
    else:
        detail = "pump on to start of stream"
        if phases.pump_on_imputed:
            detail += (
                "; pump on estimated, recording started at "
                f"{phases.recording_start_bar:.2f} bar"
            )
        lines.append(f"Pre-infusion: {phases.pre_infusion_s:.1f} s ({detail})")
    if phases.shot_time_s is None:
        lines.append("Shot time: n/a")
    else:
        lines.append(
            f"Shot time: {phases.shot_time_s:.1f} s (start of stream to pump off)"
        )
    if phases.profiled is not None and phases.end_ratio is not None:
        kind = "profiled" if phases.profiled else "natural decline"
        lines.append(
            f"Pressure profile: {kind} (ends at {phases.end_ratio:.0%} of "
            f"{phases.peak_pressure_bar:.1f} bar peak)"
        )
    if PhaseIssue.flow_before_ramp in phases.issues:
        lines.append("Note: flow started before the pressure ramp")
    if PhaseIssue.low_peak_pressure in phases.issues:
        lines.append(f"Note: peak pressure only {phases.peak_pressure_bar:.1f} bar")
    return lines
