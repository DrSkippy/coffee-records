"""Coffees blueprint — /api/coffees."""

from flask import Blueprint
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import SQLAlchemyError

from coffee_records.blueprints.crud import CrudResource, register_crud
from coffee_records.blueprints.helpers import (
    get_or_404,
    get_storage,
    require_upload,
    respond,
)
from coffee_records.database import get_session
from coffee_records.models.coffee import Coffee
from coffee_records.models.shot import Shot
from coffee_records.schemas.coffee import CoffeeCreate, CoffeeResponse, CoffeeUpdate
from coffee_records.services.storage import IMAGE_EXTENSIONS

coffees_bp = Blueprint("coffees", __name__, url_prefix="/api/coffees")

DEFAULT_IMAGE_EXTENSION = ".jpg"

# List sorted by roast_date descending (undated bags last), newest first.
register_crud(
    coffees_bp,
    "",
    CrudResource(
        model=Coffee,
        create_schema=CoffeeCreate,
        update_schema=CoffeeUpdate,
        response_schema=CoffeeResponse,
        singular="coffee",
        plural="coffees",
        label="Coffee",
        shot_column=Shot.coffee_id,
        conflict_noun="coffee",
        order_by=(Coffee.roast_date.desc().nullslast(), Coffee.created_at.desc()),
    ),
)


@coffees_bp.post("/<int:coffee_id>/image")
def upload_coffee_image(coffee_id: int) -> ResponseReturnValue:
    """Upload a label photo for a coffee.

    The new file is saved and committed before the previous one is deleted,
    so a failed commit never leaves the coffee pointing at a missing file.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON updated CoffeeResponse or 400/404.
    """
    upload = require_upload()
    storage = get_storage()
    with get_session() as session:
        coffee = get_or_404(session, Coffee, coffee_id, "Coffee")
        previous = coffee.image_filename
        new_filename = storage.save_upload(
            upload, IMAGE_EXTENSIONS, DEFAULT_IMAGE_EXTENSION
        )
        coffee.image_filename = new_filename
        try:
            session.commit()
        except SQLAlchemyError:
            storage.delete(new_filename)
            raise
        if previous:
            storage.delete(previous)
        session.refresh(coffee)
        return respond(CoffeeResponse, coffee)


@coffees_bp.delete("/<int:coffee_id>/image")
def delete_coffee_image(coffee_id: int) -> ResponseReturnValue:
    """Remove the label photo for a coffee.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON updated CoffeeResponse or 404.
    """
    with get_session() as session:
        coffee = get_or_404(session, Coffee, coffee_id, "Coffee")
        previous = coffee.image_filename
        if previous:
            coffee.image_filename = None
            session.commit()
            get_storage().delete(previous)
            session.refresh(coffee)
        return respond(CoffeeResponse, coffee)
