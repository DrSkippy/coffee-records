"""Estimate espresso shot phase boundaries from telemetry by curve fitting.

Exploration code (not used by the application); it keeps full two-segment
fits (coefficients and predictions) for plotting, which the production
implementation deliberately drops. The production counterpart is
``coffee_records/services/telemetry_phases.py`` — that module is canonical
and config-driven; change it there first and only port exploration extras
here. Each boundary is the intersection of two ideal curve segments fitted
to the signal around a transition:

* ``t_pump_on``  — pressure leaves its zero baseline (flat line ∩ rising line).
* ``t_ramp``     — pressure leaves the low pre-infusion plateau and ramps to
  brew pressure (plateau line ∩ ramp line). Reported for context only.
* ``t_flow_on``  — weight leaves its baseline (flat line ∩ rising curve).
* ``t_pump_off`` — pressure is removed (declining plateau line ∩ drop line).

From these, ``pre_infusion = t_flow_on - t_pump_on`` and
``shot_time = t_pump_off - t_flow_on``.

Every segment pair is fitted by :func:`fit_breakpoint`, a continuous
two-segment least-squares fit with a grid search over the breakpoint; the
breakpoint *is* the intersection of the two fitted segments.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from coffee_records.services.brew_time import parse_brew_time

FloatArray = NDArray[np.float64]

# Breakpoint grid resolution (s).
GRID_STEP_S = 0.05
# Pressure below this (bar) counts as "no pressure".
ZERO_PRESSURE_BAR = 0.3
# The final pressure drop starts after the last sample above this (bar);
# above sensor noise after pump-off, below a tapered shot's ~1 bar tail.
PUMP_OFF_BAR = 0.7
# A recording starting above this pressure began mid-shot and is unusable.
TRUNCATED_START_BAR = 3.0
# Weight-fit window ends when the cup holds this much (g).
FLOW_FIT_MAX_G = 4.0
# Seconds of declining plateau included before the final pressure drop.
PLATEAU_LOOKBACK_S = 2.0
# Profiled-shot detection on the brew plateau (peak + 1 s to pump-off - 0.5 s).
# Natural puck erosion ends at 72-91% of peak with a smooth (quadratic)
# decline; a modulated profile ends lower or departs from the smooth curve.
PROFILE_END_RATIO = 0.65
PROFILE_RMSE_BAR = 0.15


@dataclass
class Signal:
    """A time series sorted by time."""

    t: FloatArray
    y: FloatArray

    def window(self, start: float, end: float) -> Signal:
        """Return samples with ``start <= t <= end``."""
        mask = (self.t >= start) & (self.t <= end)
        return Signal(self.t[mask], self.y[mask])

    def first_crossing(self, level: float, after: float = -math.inf) -> float | None:
        """Return the first time at or after ``after`` where ``y >= level``."""
        idx = np.nonzero((self.y >= level) & (self.t >= after))[0]
        return float(self.t[idx[0]]) if idx.size else None

    def last_above(self, level: float) -> float | None:
        """Return the last time where ``y >= level``."""
        idx = np.nonzero(self.y >= level)[0]
        return float(self.t[idx[-1]]) if idx.size else None


@dataclass
class Telemetry:
    """Pressure and weight series from one shot file."""

    pressure: Signal
    weight: Signal
    source: str  # "beanconqueror" or "brewmeo"


@dataclass
class Breakpoint:
    """Result of a two-segment fit."""

    t0: float
    rmse: float
    coefficients: FloatArray
    left_slope: bool
    right_order: int

    def predict(self, t: FloatArray) -> FloatArray:
        """Evaluate the fitted two-segment curve."""
        return _design(t, self.t0, self.left_slope, self.right_order) @ (
            self.coefficients
        )


@dataclass
class PhaseResult:
    """Phase boundaries for one shot; ``None`` where a fit was impossible."""

    t_pump_on: float | None = None
    t_ramp: float | None = None
    t_flow_on: float | None = None
    t_pump_off: float | None = None
    pump_on_imputed: bool = False
    end_ratio: float | None = None
    plateau_rmse: float | None = None
    profiled: bool | None = None
    flags: list[str] = field(default_factory=list)
    fits: dict[str, Breakpoint] = field(default_factory=dict)

    @property
    def pre_infusion(self) -> float | None:
        """Seconds from pump on to first flow."""
        if self.t_pump_on is None or self.t_flow_on is None:
            return None
        return self.t_flow_on - self.t_pump_on

    @property
    def shot_time(self) -> float | None:
        """Seconds from first flow to pump off."""
        if self.t_flow_on is None or self.t_pump_off is None:
            return None
        return self.t_pump_off - self.t_flow_on


def _series(raw: dict[str, Any], key: str, value_field: str) -> Signal:
    """Extract one series, skipping samples without a usable value."""
    points: list[tuple[float, float]] = []
    for item in raw.get(key) or []:
        value = item.get(value_field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        try:
            points.append((parse_brew_time(item["brew_time"]), float(value)))
        except (KeyError, ValueError):
            continue
    points.sort()
    arr = np.array(points, dtype=np.float64).reshape(-1, 2)
    return Signal(arr[:, 0], arr[:, 1])


def load_telemetry(path: Path) -> Telemetry:
    """Load a stored telemetry JSON file."""
    raw = json.loads(path.read_text())
    meta = (raw.get("metadata") or {}).get("meta") or {}
    source = "brewmeo" if meta.get("Software") == "Brewmeo" else "beanconqueror"
    return Telemetry(
        pressure=_series(raw, "pressureFlow", "actual_pressure"),
        weight=_series(raw, "weight", "actual_smoothed_weight"),
        source=source,
    )


def median_filter(y: FloatArray, half_width: int = 2) -> FloatArray:
    """Running median; removes single-sample spikes (e.g. a bumped scale)."""
    if y.size == 0:
        return y
    padded = np.pad(y, half_width, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half_width + 1)
    return np.median(windows, axis=1)


def _design(t: FloatArray, t0: float, left_slope: bool, right_order: int) -> FloatArray:
    """Design matrix of a continuous two-segment curve with a knot at ``t0``.

    Left of ``t0``: constant (or line when ``left_slope``). Right of ``t0``:
    the left segment plus a polynomial in ``(t - t0)`` of ``right_order``.
    """
    hinge = np.maximum(t - t0, 0.0)
    columns = [np.ones_like(t)]
    if left_slope:
        columns.append(t)
    columns.extend(hinge**k for k in range(1, right_order + 1))
    return np.column_stack(columns)


def fit_breakpoint(
    signal: Signal,
    left_slope: bool = False,
    right_order: int = 1,
    margin_s: float = 0.2,
) -> Breakpoint | None:
    """Fit two continuous segments and return their intersection time.

    Args:
        signal: Samples spanning one transition.
        left_slope: Allow a sloped (not flat) left segment.
        right_order: Polynomial order of the right segment (1 = line).
        margin_s: Keep the breakpoint at least this far inside the window.

    Returns:
        Best breakpoint by least squares, or None if the window is too small.
    """
    t, y = signal.t, signal.y
    n_params = 1 + int(left_slope) + right_order
    if t.size < n_params + 3:
        return None
    lo, hi = t[0] + margin_s, t[-1] - margin_s
    if hi <= lo:
        return None
    best: Breakpoint | None = None
    for t0 in np.arange(lo, hi, GRID_STEP_S):
        design = _design(t, float(t0), left_slope, right_order)
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        rmse = float(np.sqrt(np.mean((design @ coef - y) ** 2)))
        if best is None or rmse < best.rmse:
            best = Breakpoint(float(t0), rmse, coef, left_slope, right_order)
    return best


def fit_pump_on(pressure: Signal, plateau: float) -> Breakpoint | None:
    """Fit the first pressure rise: zero baseline ∩ rising line."""
    reach = pressure.first_crossing(0.7 * plateau)
    if reach is None:
        return None
    return fit_breakpoint(pressure.window(-math.inf, reach))


def fit_ramp(pressure: Signal, t_start: float, peak: float) -> Breakpoint | None:
    """Fit the main ramp: low pre-infusion plateau line ∩ ramp line."""
    reach = pressure.first_crossing(0.6 * peak, after=t_start)
    if reach is None:
        return None
    return fit_breakpoint(pressure.window(t_start, reach), left_slope=True)


def fit_flow_on(
    weight: Signal, t_start: float, right_order: int = 2
) -> Breakpoint | None:
    """Fit the weight onset: flat baseline ∩ rising (quadratic) curve.

    The window runs from ``t_start`` until the cup holds ``FLOW_FIT_MAX_G``.
    Weight accelerates as flow builds, so a quadratic right segment is the
    default; ``right_order=1`` gives the plain tangent-line intersection.
    """
    reach = weight.first_crossing(FLOW_FIT_MAX_G, after=t_start)
    if reach is None:
        return None
    return fit_breakpoint(weight.window(t_start, reach), right_order=right_order)


def fit_pump_off(pressure: Signal) -> Breakpoint | None:
    """Fit the final drop: declining plateau line ∩ steep drop line.

    The drop is located by the last sample above ``PUMP_OFF_BAR`` rather than
    a fraction of peak pressure, so flow-tapered shots (pressure eased to
    ~1 bar before the pump stops) are cut at the real pump-off.
    """
    t_drop = pressure.last_above(PUMP_OFF_BAR)
    if t_drop is None:
        return None
    tail = pressure.window(t_drop, math.inf)
    below = tail.t[tail.y <= ZERO_PRESSURE_BAR]
    end = float(below[0]) + 0.3 if below.size else float(tail.t[-1])
    return fit_breakpoint(
        pressure.window(t_drop - PLATEAU_LOOKBACK_S, end), left_slope=True
    )


def classify_profile(
    pressure: Signal, t_ramp: float, t_pump_off: float, peak: float
) -> tuple[float, float, bool] | None:
    """Decide whether the brew plateau follows a modulated pressure profile.

    Args:
        pressure: Median-filtered pressure.
        t_ramp: Main-ramp breakpoint.
        t_pump_off: Pump-off breakpoint.
        peak: Peak brew pressure.

    Returns:
        ``(end_ratio, plateau_rmse, profiled)``: plateau-end pressure as a
        fraction of peak, RMS deviation (bar) from a quadratic fitted to the
        plateau, and the classification; None if the plateau is too short.
    """
    t_peak = pressure.first_crossing(0.9 * peak, after=t_ramp)
    if t_peak is None:
        return None
    grid = np.arange(t_peak + 1.0, t_pump_off - 0.5, 0.1)
    if grid.size < 20:
        return None
    y = np.interp(grid, pressure.t, pressure.y)
    end_ratio = float(np.median(y[-10:])) / peak
    coef = np.polyfit(grid, y, 2)
    rmse = float(np.sqrt(np.mean((np.polyval(coef, grid) - y) ** 2)))
    return end_ratio, rmse, end_ratio < PROFILE_END_RATIO or rmse > PROFILE_RMSE_BAR


def estimate_phases(
    telemetry: Telemetry,
    pump_on_offset: float | None = None,
    flow_right_order: int = 2,
) -> PhaseResult:
    """Estimate all phase boundaries for one shot.

    Args:
        telemetry: Loaded shot telemetry.
        pump_on_offset: For recordings that start already pressurised
            (Brewmeo auto-start), seconds between true pump-on and the
            recording start; ``t_pump_on`` is imputed as ``-offset``.
        flow_right_order: Order of the weight-rise segment.

    Returns:
        The fitted phase boundaries and any quality flags.
    """
    result = PhaseResult()
    pressure = Signal(telemetry.pressure.t, median_filter(telemetry.pressure.y))
    weight = Signal(telemetry.weight.t, median_filter(telemetry.weight.y))
    if pressure.t.size < 20:
        result.flags.append("no_pressure")
        return result
    if pressure.y[0] >= TRUNCATED_START_BAR:
        result.flags.append("truncated_start")
        return result

    peak = float(np.percentile(pressure.y, 95))
    # Low pre-infusion plateau: median pressure before the main ramp.
    ramp_reach = pressure.first_crossing(0.6 * peak)
    early = pressure.window(-math.inf, ramp_reach or math.inf)
    early_y = early.y[early.y > ZERO_PRESSURE_BAR]
    plateau = float(np.median(early_y)) if early_y.size else 1.0

    if pressure.y[0] < ZERO_PRESSURE_BAR:
        fit = fit_pump_on(pressure, plateau)
        if fit is not None:
            result.t_pump_on = fit.t0
            result.fits["pump_on"] = fit
    elif pump_on_offset is not None:
        result.t_pump_on = -pump_on_offset
        result.pump_on_imputed = True
    else:
        result.flags.append("starts_pressurised")

    ramp = fit_ramp(pressure, (result.t_pump_on or 0.0) + 0.5, peak)
    if ramp is not None:
        result.t_ramp = ramp.t0
        result.fits["ramp"] = ramp

    flow = fit_flow_on(weight, result.t_pump_on or 0.0, flow_right_order)
    if flow is not None:
        result.t_flow_on = flow.t0
        result.fits["flow_on"] = flow

    off = fit_pump_off(pressure)
    if off is not None:
        result.t_pump_off = off.t0
        result.fits["pump_off"] = off

    if result.t_ramp is not None and result.t_pump_off is not None:
        profile = classify_profile(pressure, result.t_ramp, result.t_pump_off, peak)
        if profile is not None:
            result.end_ratio, result.plateau_rmse, result.profiled = profile

    if peak < 6.0:
        result.flags.append("low_peak_pressure")
    if result.t_flow_on is not None and result.t_ramp is not None:
        if result.t_flow_on < result.t_ramp - 1.0:
            result.flags.append("flow_before_ramp")
    return result
