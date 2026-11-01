"""Pydantic schemas for values derived from shot telemetry."""

from enum import Enum

from pydantic import BaseModel


class PhaseIssue(str, Enum):
    """Why a phase estimate is missing or needs care."""

    no_pressure = "no_pressure"
    truncated_start = "truncated_start"
    no_pump_on = "no_pump_on"
    no_flow_on = "no_flow_on"
    no_pump_off = "no_pump_off"
    low_peak_pressure = "low_peak_pressure"
    flow_before_ramp = "flow_before_ramp"


class TelemetryPhases(BaseModel):
    """Shot phase boundaries fitted from pressure and weight telemetry.

    Times are seconds on the telemetry clock. ``pre_infusion_s`` runs from
    pump on to the start of the steady stream; ``shot_time_s`` from the start
    of the stream to pump off. Either is None when it cannot be estimated
    (e.g. a recording that started mid-shot).
    """

    pre_infusion_s: float | None = None
    shot_time_s: float | None = None
    t_pump_on: float | None = None
    t_ramp: float | None = None
    t_flow_on: float | None = None
    t_pump_off: float | None = None
    pump_on_imputed: bool = False
    recording_start_bar: float | None = None
    peak_pressure_bar: float | None = None
    profiled: bool | None = None
    end_ratio: float | None = None
    plateau_rmse_bar: float | None = None
    issues: list[PhaseIssue] = []
