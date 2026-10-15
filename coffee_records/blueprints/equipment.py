"""Equipment blueprint — /api/grinders, /api/brewing-devices, /api/scales."""

from flask import Blueprint

from coffee_records.blueprints.crud import CrudResource, register_crud
from coffee_records.models.equipment import BrewingDevice, Grinder, Scale
from coffee_records.models.shot import Shot
from coffee_records.schemas.equipment import (
    BrewingDeviceCreate,
    BrewingDeviceResponse,
    BrewingDeviceUpdate,
    GrinderCreate,
    GrinderResponse,
    GrinderUpdate,
    ScaleCreate,
    ScaleResponse,
    ScaleUpdate,
)

equipment_bp = Blueprint("equipment", __name__, url_prefix="/api")


# ── Grinders ──────────────────────────────────────────────────────────────────

register_crud(
    equipment_bp,
    "/grinders",
    CrudResource(
        model=Grinder,
        create_schema=GrinderCreate,
        update_schema=GrinderUpdate,
        response_schema=GrinderResponse,
        singular="grinder",
        plural="grinders",
        label="Grinder",
        shot_column=Shot.grinder_id,
        conflict_noun="grinder",
        order_by=(Grinder.make, Grinder.model),
    ),
)

# ── Brewing Devices ───────────────────────────────────────────────────────────

register_crud(
    equipment_bp,
    "/brewing-devices",
    CrudResource(
        model=BrewingDevice,
        create_schema=BrewingDeviceCreate,
        update_schema=BrewingDeviceUpdate,
        response_schema=BrewingDeviceResponse,
        singular="brewing_device",
        plural="brewing_devices",
        label="Brewing device",
        shot_column=Shot.device_id,
        conflict_noun="device",
        order_by=(BrewingDevice.make, BrewingDevice.model),
    ),
)

# ── Scales ────────────────────────────────────────────────────────────────────

register_crud(
    equipment_bp,
    "/scales",
    CrudResource(
        model=Scale,
        create_schema=ScaleCreate,
        update_schema=ScaleUpdate,
        response_schema=ScaleResponse,
        singular="scale",
        plural="scales",
        label="Scale",
        shot_column=Shot.scale_id,
        conflict_noun="scale",
        order_by=(Scale.make, Scale.model),
    ),
)
