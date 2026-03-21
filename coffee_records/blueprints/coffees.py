"""Coffees blueprint — /api/coffees."""

import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage

from coffee_records.config import Config
from coffee_records.database import get_session
from coffee_records.models.coffee import Coffee
from coffee_records.models.shot import Shot
from coffee_records.schemas.coffee import CoffeeCreate, CoffeeResponse, CoffeeUpdate

coffees_bp = Blueprint("coffees", __name__, url_prefix="/api/coffees")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _cfg() -> Config:
    """Return the application config."""
    return current_app.config["APP_CONFIG"]  # type: ignore[return-value]


def _save_image(file: FileStorage, cfg: Config) -> str:
    """Save an uploaded image and return its filename.

    Args:
        file: The uploaded file object.
        cfg: Application config.

    Returns:
        The saved filename (UUID-based).
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    dest = Path(cfg.uploads.coffee_image_dir)
    dest.mkdir(parents=True, exist_ok=True)
    file.save(dest / filename)
    return filename


def _delete_image_file(filename: str, cfg: Config) -> None:
    """Delete an image file from disk if it exists.

    Args:
        filename: The filename to delete.
        cfg: Application config.
    """
    path = Path(cfg.uploads.coffee_image_dir) / filename
    if path.exists():
        path.unlink()


@coffees_bp.get("")
def list_coffees() -> object:
    """List all coffees sorted by roast_date descending.

    Returns:
        JSON array of CoffeeResponse objects.
    """
    with get_session() as session:
        coffees = (
            session.query(Coffee)
            .order_by(Coffee.roast_date.desc().nullslast(), Coffee.created_at.desc())
            .all()
        )
        return jsonify([CoffeeResponse.model_validate(c).model_dump(mode="json") for c in coffees])


@coffees_bp.post("")
def create_coffee() -> object:
    """Create a new coffee.

    Returns:
        JSON CoffeeResponse with 201 status.
    """
    payload = CoffeeCreate.model_validate(request.get_json())
    with get_session() as session:
        coffee = Coffee(**payload.model_dump())
        session.add(coffee)
        session.commit()
        session.refresh(coffee)
        return jsonify(CoffeeResponse.model_validate(coffee).model_dump(mode="json")), 201


@coffees_bp.get("/<int:coffee_id>")
def get_coffee(coffee_id: int) -> object:
    """Get a single coffee by ID.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON CoffeeResponse or 404.
    """
    with get_session() as session:
        coffee = session.get(Coffee, coffee_id)
        if coffee is None:
            return jsonify({"error": "Coffee not found"}), 404
        return jsonify(CoffeeResponse.model_validate(coffee).model_dump(mode="json"))


@coffees_bp.put("/<int:coffee_id>")
def update_coffee(coffee_id: int) -> object:
    """Update a coffee.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON updated CoffeeResponse or 404.
    """
    payload = CoffeeUpdate.model_validate(request.get_json())
    with get_session() as session:
        coffee = session.get(Coffee, coffee_id)
        if coffee is None:
            return jsonify({"error": "Coffee not found"}), 404
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(coffee, field, value)
        session.commit()
        session.refresh(coffee)
        return jsonify(CoffeeResponse.model_validate(coffee).model_dump(mode="json"))


@coffees_bp.delete("/<int:coffee_id>")
def delete_coffee(coffee_id: int) -> object:
    """Delete a coffee. Returns 409 if shots reference this coffee.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        204 on success, 404 if not found, 409 if shots exist.
    """
    with get_session() as session:
        coffee = session.get(Coffee, coffee_id)
        if coffee is None:
            return jsonify({"error": "Coffee not found"}), 404
        shot_count = session.query(Shot).filter(Shot.coffee_id == coffee_id).count()
        if shot_count > 0:
            return (
                jsonify({"error": f"Cannot delete: {shot_count} shot(s) reference this coffee"}),
                409,
            )
        session.delete(coffee)
        session.commit()
        return "", 204


@coffees_bp.post("/<int:coffee_id>/image")
def upload_coffee_image(coffee_id: int) -> object:
    """Upload a label photo for a coffee.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON updated CoffeeResponse or 400/404.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    cfg = _cfg()
    with get_session() as session:
        coffee = session.get(Coffee, coffee_id)
        if coffee is None:
            return jsonify({"error": "Coffee not found"}), 404
        if coffee.image_filename:
            _delete_image_file(coffee.image_filename, cfg)
        coffee.image_filename = _save_image(file, cfg)
        session.commit()
        session.refresh(coffee)
        return jsonify(CoffeeResponse.model_validate(coffee).model_dump(mode="json"))


@coffees_bp.delete("/<int:coffee_id>/image")
def delete_coffee_image(coffee_id: int) -> object:
    """Remove the label photo for a coffee.

    Args:
        coffee_id: The coffee's primary key.

    Returns:
        JSON updated CoffeeResponse or 404.
    """
    cfg = _cfg()
    with get_session() as session:
        coffee = session.get(Coffee, coffee_id)
        if coffee is None:
            return jsonify({"error": "Coffee not found"}), 404
        if coffee.image_filename:
            _delete_image_file(coffee.image_filename, cfg)
            coffee.image_filename = None
            session.commit()
            session.refresh(coffee)
        return jsonify(CoffeeResponse.model_validate(coffee).model_dump(mode="json"))


def _get_session_ctx() -> Session:
    """Helper for typed session access (used in tests)."""
    return get_session()
