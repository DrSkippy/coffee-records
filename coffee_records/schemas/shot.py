"""Pydantic schemas for Shot."""

from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel

from coffee_records.models.shot import DrinkType


class ShotCreate(BaseModel):
    """Payload for creating a shot."""

    date: Date
    maker: str
    coffee_id: int | None = None
    dose_weight: float | None = None
    pre_infusion_time: str | None = None
    extraction_time: float | None = None
    scale_id: int | None = None
    final_weight: float | None = None
    drink_type: DrinkType | None = None
    grinder_temp_before: float | None = None
    grinder_temp_after: float | None = None
    wedge: bool = False
    shaker: bool = False
    wdt: bool = False
    flow_taper: bool = False
    grind_setting: str | None = None
    notes: str | None = None
    grinder_id: int | None = None
    device_id: int | None = None


class ShotUpdate(BaseModel):
    """Payload for updating a shot (all fields optional)."""

    date: Date | None = None
    maker: str | None = None
    coffee_id: int | None = None
    dose_weight: float | None = None
    pre_infusion_time: str | None = None
    extraction_time: float | None = None
    scale_id: int | None = None
    final_weight: float | None = None
    drink_type: DrinkType | None = None
    grinder_temp_before: float | None = None
    grinder_temp_after: float | None = None
    wedge: bool | None = None
    shaker: bool | None = None
    wdt: bool | None = None
    flow_taper: bool | None = None
    grind_setting: str | None = None
    notes: str | None = None
    grinder_id: int | None = None
    device_id: int | None = None


class ShotResponse(BaseModel):
    """Shot response schema with denormalized labels."""

    id: int
    date: Date
    maker: str
    coffee_id: int | None
    coffee_name: str | None
    dose_weight: float | None
    pre_infusion_time: str | None
    extraction_time: float | None
    scale_id: int | None
    scale_label: str | None
    final_weight: float | None
    drink_type: DrinkType | None
    grinder_temp_before: float | None
    grinder_temp_after: float | None
    wedge: bool
    shaker: bool
    wdt: bool
    flow_taper: bool
    grind_setting: str | None
    notes: str | None
    video_filename: str | None
    grinder_id: int | None
    grinder_label: str | None
    device_id: int | None
    device_label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_shot(cls, shot: object) -> "ShotResponse":
        """Build a ShotResponse with denormalized labels from a Shot ORM instance.

        Args:
            shot: A Shot ORM model instance.

        Returns:
            ShotResponse with all denormalized labels populated.
        """
        from coffee_records.models.shot import Shot

        s: Shot = shot  # type: ignore[assignment]
        coffee_name = s.coffee.name if s.coffee else None
        grinder_label = (
            f"{s.grinder.make} {s.grinder.model}" if s.grinder else None
        )
        device_label = f"{s.device.make} {s.device.model}" if s.device else None
        scale_label = f"{s.scale.make} {s.scale.model}" if s.scale else None

        return cls(
            id=s.id,
            date=s.date,
            maker=s.maker,
            coffee_id=s.coffee_id,
            coffee_name=coffee_name,
            dose_weight=s.dose_weight,
            pre_infusion_time=s.pre_infusion_time,
            extraction_time=s.extraction_time,
            scale_id=s.scale_id,
            scale_label=scale_label,
            final_weight=s.final_weight,
            drink_type=s.drink_type,
            grinder_temp_before=s.grinder_temp_before,
            grinder_temp_after=s.grinder_temp_after,
            wedge=s.wedge,
            shaker=s.shaker,
            wdt=s.wdt,
            flow_taper=s.flow_taper,
            grind_setting=s.grind_setting,
            notes=s.notes,
            video_filename=s.video_filename,
            grinder_id=s.grinder_id,
            grinder_label=grinder_label,
            device_id=s.device_id,
            device_label=device_label,
            created_at=s.created_at,
        )
