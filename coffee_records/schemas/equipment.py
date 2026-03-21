"""Pydantic schemas for equipment (Grinder, BrewingDevice, Scale)."""

from datetime import datetime

from pydantic import BaseModel

from coffee_records.models.equipment import GrinderType


class GrinderCreate(BaseModel):
    """Payload for creating a grinder."""

    make: str
    model: str
    type: GrinderType
    notes: str | None = None


class GrinderUpdate(BaseModel):
    """Payload for updating a grinder."""

    make: str | None = None
    model: str | None = None
    type: GrinderType | None = None
    notes: str | None = None


class GrinderResponse(BaseModel):
    """Grinder response schema."""

    id: int
    make: str
    model: str
    type: GrinderType
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BrewingDeviceCreate(BaseModel):
    """Payload for creating a brewing device."""

    make: str
    model: str
    type: str
    warmup_minutes: float | None = None
    notes: str | None = None


class BrewingDeviceUpdate(BaseModel):
    """Payload for updating a brewing device."""

    make: str | None = None
    model: str | None = None
    type: str | None = None
    warmup_minutes: float | None = None
    notes: str | None = None


class BrewingDeviceResponse(BaseModel):
    """BrewingDevice response schema."""

    id: int
    make: str
    model: str
    type: str
    warmup_minutes: float | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScaleCreate(BaseModel):
    """Payload for creating a scale."""

    make: str
    model: str
    notes: str | None = None


class ScaleUpdate(BaseModel):
    """Payload for updating a scale."""

    make: str | None = None
    model: str | None = None
    notes: str | None = None


class ScaleResponse(BaseModel):
    """Scale response schema."""

    id: int
    make: str
    model: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
