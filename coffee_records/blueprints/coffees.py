"""Coffees blueprint — /api/coffees."""

from flask import Blueprint, jsonify, request
from sqlalchemy.orm import Session

from coffee_records.database import get_session
from coffee_records.models.coffee import Coffee
from coffee_records.models.shot import Shot
from coffee_records.schemas.coffee import CoffeeCreate, CoffeeResponse, CoffeeUpdate

coffees_bp = Blueprint("coffees", __name__, url_prefix="/api/coffees")


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


def _get_session_ctx() -> Session:
    """Helper for typed session access (used in tests)."""
    return get_session()
