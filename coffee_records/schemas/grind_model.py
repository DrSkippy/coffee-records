"""Pydantic schemas for grind model training results."""

from datetime import datetime

from pydantic import BaseModel


class CoffeeInterceptItem(BaseModel):
    """Per-coffee intercept within a training run."""

    coffee_id: int
    coffee_name: str | None
    intercept: float


class GrindModelPoint(BaseModel):
    """One data point used in training, projected for plotting."""

    shot_id: int
    date: str
    age_days: int
    temp_offset: float       # grinder_temp_before - 65
    grind: float             # actual parsed grind setting (numeric)
    grind_str: str           # human-readable (e.g. "8+5")
    grind_predicted: float   # model prediction
    grind_predicted_str: str


class GrindModelTrainingResponse(BaseModel):
    """Response shape for a completed training run."""

    training_id: int
    grinder_id: int
    grinder_label: str
    trained_at: datetime
    n_shots_available: int
    n_shots_used: int
    n_coffees: int
    n_iterations: int
    converged: bool
    r_squared: float | None
    a0: float  # grinder_temp - 65
    a2: float  # extraction_time - target_shot_time
    a3: float  # dose_weight - 20
    a4: float  # age_days
    a5: float  # final_weight - 2*dose
    coffee_intercepts: list[CoffeeInterceptItem]


class TargetTimeItem(BaseModel):
    """Per-coffee target shot time (WMA) for use in the shot planner."""

    coffee_id: int
    target_shot_time: float | None


class GrindModelParamsResponse(GrindModelTrainingResponse):
    """Training response augmented with per-shot data points for plotting."""

    points: list[GrindModelPoint]
    target_times: list[TargetTimeItem]
