"""Pydantic schemas for ShotDefaults."""

from datetime import datetime

from pydantic import BaseModel


class ShotDefaultsResponse(BaseModel):
    """Response schema for GET /api/defaults."""

    id: int
    maker: str
    dose_weight: float | None
    pre_infusion_time: str | None
    extraction_time: float | None
    final_weight: float | None
    drink_type: str | None
    grinder_temp_before: float | None
    wedge: bool
    shaker: bool
    wdt: bool
    flow_taper: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShotDefaultsUpdate(BaseModel):
    """Payload for PUT /api/defaults — full replacement semantics."""

    maker: str
    dose_weight: float | None = None
    pre_infusion_time: str | None = None
    extraction_time: float | None = None
    final_weight: float | None = None
    drink_type: str | None = None
    grinder_temp_before: float | None = None
    wedge: bool = False
    shaker: bool = False
    wdt: bool = False
    flow_taper: bool = False
