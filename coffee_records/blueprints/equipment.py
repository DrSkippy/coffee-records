"""Equipment blueprint — /api/grinders, /api/brewing-devices, /api/scales."""

from flask import Blueprint, jsonify, request

from coffee_records.database import get_session
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


@equipment_bp.get("/grinders")
def list_grinders() -> object:
    """List all grinders."""
    with get_session() as session:
        grinders = session.query(Grinder).order_by(Grinder.make, Grinder.model).all()
        return jsonify([GrinderResponse.model_validate(g).model_dump(mode="json") for g in grinders])


@equipment_bp.post("/grinders")
def create_grinder() -> object:
    """Create a grinder."""
    payload = GrinderCreate.model_validate(request.get_json())
    with get_session() as session:
        grinder = Grinder(**payload.model_dump())
        session.add(grinder)
        session.commit()
        session.refresh(grinder)
        return jsonify(GrinderResponse.model_validate(grinder).model_dump(mode="json")), 201


@equipment_bp.get("/grinders/<int:grinder_id>")
def get_grinder(grinder_id: int) -> object:
    """Get a grinder by ID."""
    with get_session() as session:
        grinder = session.get(Grinder, grinder_id)
        if grinder is None:
            return jsonify({"error": "Grinder not found"}), 404
        return jsonify(GrinderResponse.model_validate(grinder).model_dump(mode="json"))


@equipment_bp.put("/grinders/<int:grinder_id>")
def update_grinder(grinder_id: int) -> object:
    """Update a grinder."""
    payload = GrinderUpdate.model_validate(request.get_json())
    with get_session() as session:
        grinder = session.get(Grinder, grinder_id)
        if grinder is None:
            return jsonify({"error": "Grinder not found"}), 404
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(grinder, field, value)
        session.commit()
        session.refresh(grinder)
        return jsonify(GrinderResponse.model_validate(grinder).model_dump(mode="json"))


@equipment_bp.delete("/grinders/<int:grinder_id>")
def delete_grinder(grinder_id: int) -> object:
    """Delete a grinder. Returns 409 if shots reference it."""
    with get_session() as session:
        grinder = session.get(Grinder, grinder_id)
        if grinder is None:
            return jsonify({"error": "Grinder not found"}), 404
        count = session.query(Shot).filter(Shot.grinder_id == grinder_id).count()
        if count > 0:
            return jsonify({"error": f"Cannot delete: {count} shot(s) reference this grinder"}), 409
        session.delete(grinder)
        session.commit()
        return "", 204


# ── Brewing Devices ───────────────────────────────────────────────────────────


@equipment_bp.get("/brewing-devices")
def list_brewing_devices() -> object:
    """List all brewing devices."""
    with get_session() as session:
        devices = (
            session.query(BrewingDevice).order_by(BrewingDevice.make, BrewingDevice.model).all()
        )
        return jsonify(
            [BrewingDeviceResponse.model_validate(d).model_dump(mode="json") for d in devices]
        )


@equipment_bp.post("/brewing-devices")
def create_brewing_device() -> object:
    """Create a brewing device."""
    payload = BrewingDeviceCreate.model_validate(request.get_json())
    with get_session() as session:
        device = BrewingDevice(**payload.model_dump())
        session.add(device)
        session.commit()
        session.refresh(device)
        return (
            jsonify(BrewingDeviceResponse.model_validate(device).model_dump(mode="json")),
            201,
        )


@equipment_bp.get("/brewing-devices/<int:device_id>")
def get_brewing_device(device_id: int) -> object:
    """Get a brewing device by ID."""
    with get_session() as session:
        device = session.get(BrewingDevice, device_id)
        if device is None:
            return jsonify({"error": "Brewing device not found"}), 404
        return jsonify(BrewingDeviceResponse.model_validate(device).model_dump(mode="json"))


@equipment_bp.put("/brewing-devices/<int:device_id>")
def update_brewing_device(device_id: int) -> object:
    """Update a brewing device."""
    payload = BrewingDeviceUpdate.model_validate(request.get_json())
    with get_session() as session:
        device = session.get(BrewingDevice, device_id)
        if device is None:
            return jsonify({"error": "Brewing device not found"}), 404
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(device, field, value)
        session.commit()
        session.refresh(device)
        return jsonify(BrewingDeviceResponse.model_validate(device).model_dump(mode="json"))


@equipment_bp.delete("/brewing-devices/<int:device_id>")
def delete_brewing_device(device_id: int) -> object:
    """Delete a brewing device. Returns 409 if shots reference it."""
    with get_session() as session:
        device = session.get(BrewingDevice, device_id)
        if device is None:
            return jsonify({"error": "Brewing device not found"}), 404
        count = session.query(Shot).filter(Shot.device_id == device_id).count()
        if count > 0:
            return (
                jsonify({"error": f"Cannot delete: {count} shot(s) reference this device"}),
                409,
            )
        session.delete(device)
        session.commit()
        return "", 204


# ── Scales ────────────────────────────────────────────────────────────────────


@equipment_bp.get("/scales")
def list_scales() -> object:
    """List all scales."""
    with get_session() as session:
        scales = session.query(Scale).order_by(Scale.make, Scale.model).all()
        return jsonify([ScaleResponse.model_validate(s).model_dump(mode="json") for s in scales])


@equipment_bp.post("/scales")
def create_scale() -> object:
    """Create a scale."""
    payload = ScaleCreate.model_validate(request.get_json())
    with get_session() as session:
        scale = Scale(**payload.model_dump())
        session.add(scale)
        session.commit()
        session.refresh(scale)
        return jsonify(ScaleResponse.model_validate(scale).model_dump(mode="json")), 201


@equipment_bp.get("/scales/<int:scale_id>")
def get_scale(scale_id: int) -> object:
    """Get a scale by ID."""
    with get_session() as session:
        scale = session.get(Scale, scale_id)
        if scale is None:
            return jsonify({"error": "Scale not found"}), 404
        return jsonify(ScaleResponse.model_validate(scale).model_dump(mode="json"))


@equipment_bp.put("/scales/<int:scale_id>")
def update_scale(scale_id: int) -> object:
    """Update a scale."""
    payload = ScaleUpdate.model_validate(request.get_json())
    with get_session() as session:
        scale = session.get(Scale, scale_id)
        if scale is None:
            return jsonify({"error": "Scale not found"}), 404
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(scale, field, value)
        session.commit()
        session.refresh(scale)
        return jsonify(ScaleResponse.model_validate(scale).model_dump(mode="json"))


@equipment_bp.delete("/scales/<int:scale_id>")
def delete_scale(scale_id: int) -> object:
    """Delete a scale. Returns 409 if shots reference it."""
    with get_session() as session:
        scale = session.get(Scale, scale_id)
        if scale is None:
            return jsonify({"error": "Scale not found"}), 404
        count = session.query(Shot).filter(Shot.scale_id == scale_id).count()
        if count > 0:
            return jsonify({"error": f"Cannot delete: {count} shot(s) reference this scale"}), 409
        session.delete(scale)
        session.commit()
        return "", 204
