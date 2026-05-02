"""Defaults blueprint — /api/defaults."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from coffee_records.database import get_session
from coffee_records.models.settings import ShotDefaults
from coffee_records.schemas.settings import ShotDefaultsResponse, ShotDefaultsUpdate

defaults_bp = Blueprint("defaults", __name__, url_prefix="/api/defaults")

_SEED_DEFAULTS: dict[str, object] = dict(
    maker="Scott",
    dose_weight=20.0,
    pre_infusion_time="5+5",
    extraction_time=28.0,
    final_weight=40.0,
    drink_type="americano",
    grinder_temp_before=64.0,
    wedge=True,
    shaker=True,
    wdt=True,
    flow_taper=False,
)


@defaults_bp.get("")
def get_defaults() -> object:
    """Return the current shot defaults, creating the singleton row if absent."""
    with get_session() as session:
        row = session.get(ShotDefaults, 1)
        if row is None:
            row = ShotDefaults(id=1, **_SEED_DEFAULTS)
            session.add(row)
            session.commit()
            session.refresh(row)
        return jsonify(ShotDefaultsResponse.model_validate(row).model_dump(mode="json"))


@defaults_bp.put("")
def update_defaults() -> object:
    """Update the shot defaults (upsert at id=1)."""
    payload = ShotDefaultsUpdate.model_validate(request.get_json())
    with get_session() as session:
        row = session.get(ShotDefaults, 1)
        if row is None:
            row = ShotDefaults(id=1, **payload.model_dump())
            session.add(row)
        else:
            for field, value in payload.model_dump().items():
                setattr(row, field, value)
            row.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(row)
        return jsonify(ShotDefaultsResponse.model_validate(row).model_dump(mode="json"))
