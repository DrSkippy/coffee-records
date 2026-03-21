"""Pydantic schemas for Coffee."""

from datetime import date, datetime

from pydantic import BaseModel

from coffee_records.models.coffee import RoastLevel


class CoffeeCreate(BaseModel):
    """Payload for creating a coffee."""

    name: str
    roaster: str
    roast_date: date | None = None
    origin_country: str | None = None
    roast_level: RoastLevel | None = None
    variety: str | None = None
    process: str | None = None


class CoffeeUpdate(BaseModel):
    """Payload for updating a coffee (all fields optional)."""

    name: str | None = None
    roaster: str | None = None
    roast_date: date | None = None
    origin_country: str | None = None
    roast_level: RoastLevel | None = None
    variety: str | None = None
    process: str | None = None


class CoffeeResponse(BaseModel):
    """Coffee response schema."""

    id: int
    name: str
    roaster: str
    roast_date: date | None
    origin_country: str | None
    roast_level: RoastLevel | None
    variety: str | None
    process: str | None
    image_filename: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
