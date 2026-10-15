"""Report services: trends, target shot time and grind regression."""

from coffee_records.services.reports.filters import ShotFilter
from coffee_records.services.reports.regression import grind_regression
from coffee_records.services.reports.target_time import (
    target_shot_time_wma,
    target_shot_times_wma,
)
from coffee_records.services.reports.trends import (
    by_coffee,
    dose_yield_over_time,
    extraction_trends,
    shots_per_day,
    shots_per_grinder,
)

__all__ = [
    "ShotFilter",
    "by_coffee",
    "dose_yield_over_time",
    "extraction_trends",
    "grind_regression",
    "shots_per_day",
    "shots_per_grinder",
    "target_shot_time_wma",
    "target_shot_times_wma",
]
