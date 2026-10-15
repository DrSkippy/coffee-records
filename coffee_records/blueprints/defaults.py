"""Defaults blueprint — /api/defaults."""

from datetime import datetime, timezone

from flask import Blueprint, request
from flask.typing import ResponseReturnValue

from coffee_records.blueprints.helpers import get_config, respond
from coffee_records.database import get_session
from coffee_records.models.settings import SHOT_DEFAULTS_ID, ShotDefaults
from coffee_records.schemas.settings import ShotDefaultsResponse, ShotDefaultsUpdate

defaults_bp = Blueprint("defaults", __name__, url_prefix="/api/defaults")


@defaults_bp.get("")
def get_defaults() -> ResponseReturnValue:
    """Return the current shot defaults, creating the singleton row if absent.

    The row is seeded from config.yaml's ``shot_defaults_seed`` block.
    """
    with get_session() as session:
        row = session.get(ShotDefaults, SHOT_DEFAULTS_ID)
        if row is None:
            seed = get_config().shot_defaults_seed.model_dump()
            row = ShotDefaults(id=SHOT_DEFAULTS_ID, **seed)
            session.add(row)
            session.commit()
            session.refresh(row)
        return respond(ShotDefaultsResponse, row)


@defaults_bp.put("")
def update_defaults() -> ResponseReturnValue:
    """Update the shot defaults (full replacement, upsert at the singleton id)."""
    payload = ShotDefaultsUpdate.model_validate(request.get_json())
    with get_session() as session:
        row = session.get(ShotDefaults, SHOT_DEFAULTS_ID)
        if row is None:
            row = ShotDefaults(id=SHOT_DEFAULTS_ID, **payload.model_dump())
            session.add(row)
        else:
            for field, value in payload.model_dump().items():
                setattr(row, field, value)
            row.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(row)
        return respond(ShotDefaultsResponse, row)
