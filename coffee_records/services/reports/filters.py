"""Shared shot filtering for report queries."""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any, TypeVar

from sqlalchemy.orm import Query

from coffee_records.models.shot import Shot

RowT = TypeVar("RowT", bound=Any)


@dataclass(frozen=True)
class ShotFilter:
    """Optional date range and equipment/coffee filters applied to Shot queries.

    Attributes:
        date_from: Inclusive start date.
        date_to: Inclusive end date.
        coffee_id: Restrict to one coffee bag.
        grinder_id: Restrict to one grinder.
        device_id: Restrict to one brewing device.
    """

    date_from: date | None = None
    date_to: date | None = None
    coffee_id: int | None = None
    grinder_id: int | None = None
    device_id: int | None = None

    def with_default_range(self, days: int, today: date | None = None) -> "ShotFilter":
        """Fill a missing start/end date with the trailing ``days`` window.

        Args:
            days: Window length ending today.
            today: Override for the current date (tests).

        Returns:
            A filter whose dates are both set.
        """
        today = today or date.today()
        return replace(
            self,
            date_from=self.date_from or today - timedelta(days=days),
            date_to=self.date_to or today,
        )

    def apply(self, query: "Query[RowT]") -> "Query[RowT]":
        """Add a WHERE clause for every set filter.

        Args:
            query: A query selecting from (or joined to) Shot.

        Returns:
            The filtered query.
        """
        if self.date_from is not None:
            query = query.filter(Shot.date >= self.date_from)
        if self.date_to is not None:
            query = query.filter(Shot.date <= self.date_to)
        if self.coffee_id is not None:
            query = query.filter(Shot.coffee_id == self.coffee_id)
        if self.grinder_id is not None:
            query = query.filter(Shot.grinder_id == self.grinder_id)
        if self.device_id is not None:
            query = query.filter(Shot.device_id == self.device_id)
        return query


def equipment_label(make: str | None, model: str | None) -> str | None:
    """Return "make model", or None when the equipment is absent.

    Args:
        make: Equipment make (None for an outer-joined missing row).
        model: Equipment model.

    Returns:
        Display label or None.
    """
    return f"{make} {model}" if make else None
