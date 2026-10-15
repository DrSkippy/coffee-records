"""Pydantic response schemas for the trend and regression reports."""

from datetime import date as Date

from pydantic import BaseModel


class DoseYieldPoint(BaseModel):
    """One shot's dose, yield and brew ratio."""

    date: Date
    shot_id: int
    dose_weight: float
    final_weight: float
    ratio: float | None
    device_id: int | None
    device_label: str | None


class ShotsPerDayPoint(BaseModel):
    """Shot count for one day."""

    date: Date
    count: int


class ExtractionPoint(BaseModel):
    """One shot's extraction time."""

    date: Date
    shot_id: int
    extraction_time: float
    device_id: int | None
    device_label: str | None


class GrinderShotCount(BaseModel):
    """Shot count for one grinder."""

    grinder_id: int
    make: str
    model: str
    count: int


class CoffeeShotSummary(BaseModel):
    """Per-shot row in the by-coffee report."""

    date: Date
    shot_id: int
    dose_weight: float | None
    final_weight: float | None
    extraction_time: float | None


class ByCoffeeReport(BaseModel):
    """Aggregate stats and shot list for one coffee bag."""

    coffee_id: int
    total_shots: int
    avg_dose: float | None
    avg_final_weight: float | None
    avg_extraction_time: float | None
    avg_ratio: float | None
    shots: list[CoffeeShotSummary]


class TargetShotTimeResponse(BaseModel):
    """Weighted moving average target shot time and the filters used."""

    coffee_id: int
    grinder_id: int | None
    device_id: int | None
    target_shot_time: float | None
    n_shots: int


class RegressionCoefficients(BaseModel):
    """Coefficients of ``y = a*x1 + b*x2 + c``."""

    a: float
    b: float
    c: float


class RegressionPoint(BaseModel):
    """One shot in a grind regression, with its fitted value."""

    shot_id: int
    date: Date
    x1: int  # days since roast
    x2: float  # grinder temperature offset from the reference
    y: float
    y_str: str
    y_predicted: float
    y_predicted_str: str


class GrinderRegression(BaseModel):
    """Regression result for one grinder."""

    grinder_id: int
    grinder_label: str
    n_shots: int
    coefficients: RegressionCoefficients
    r_squared: float | None
    points: list[RegressionPoint]


class GrindRegressionResponse(BaseModel):
    """Grind regression results for one coffee bag."""

    coffee_id: int
    roast_date: Date
    grinders: list[GrinderRegression]
    target_shot_time: float | None
