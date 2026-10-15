"""Generic list/create/get/update/delete routes for simple resources."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import BaseModel
from sqlalchemy.orm import InstrumentedAttribute

from coffee_records.blueprints.helpers import (
    apply_updates,
    ensure_no_shots_reference,
    get_or_404,
    respond,
)
from coffee_records.database import Base, get_session


@dataclass(frozen=True)
class CrudResource:
    """Describes one CRUD resource and how it relates to shots.

    Attributes:
        model: ORM model class.
        create_schema: Pydantic payload for POST.
        update_schema: Pydantic partial payload for PUT.
        response_schema: Pydantic response model.
        singular: snake_case singular name, used for endpoint names.
        plural: snake_case plural name, used for the list endpoint name.
        label: Display name used in "<label> not found".
        shot_column: Shot foreign key that blocks deletion when referenced.
        conflict_noun: Word used in the 409 message.
        order_by: Ordering for the list endpoint.
    """

    model: type[Base]
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    response_schema: type[BaseModel]
    singular: str
    plural: str
    label: str
    shot_column: InstrumentedAttribute[Any]
    conflict_noun: str
    order_by: tuple[Any, ...]


def register_crud(blueprint: Blueprint, rule: str, resource: CrudResource) -> None:
    """Register the five CRUD routes for a resource on a blueprint.

    Routes: ``GET rule``, ``POST rule``, ``GET rule/<id>``, ``PUT rule/<id>``
    and ``DELETE rule/<id>``. Endpoint names follow ``list_<plural>``,
    ``create_<singular>``, ``get_<singular>``, ``update_<singular>`` and
    ``delete_<singular>``.

    Args:
        blueprint: Blueprint to register on.
        rule: Collection URL rule relative to the blueprint prefix ("" allowed).
        resource: Resource description.
    """
    item_rule = f"{rule}/<int:pk>"

    def list_items() -> ResponseReturnValue:
        """List all items in the configured order."""
        with get_session() as session:
            items = session.query(resource.model).order_by(*resource.order_by).all()
            return jsonify(
                [
                    resource.response_schema.model_validate(item).model_dump(
                        mode="json"
                    )
                    for item in items
                ]
            )

    def create_item() -> ResponseReturnValue:
        """Create an item from the JSON body."""
        payload = resource.create_schema.model_validate(request.get_json())
        with get_session() as session:
            item = resource.model(**payload.model_dump())
            session.add(item)
            session.commit()
            session.refresh(item)
            return respond(resource.response_schema, item, HTTPStatus.CREATED)

    def get_item(pk: int) -> ResponseReturnValue:
        """Return one item or 404."""
        with get_session() as session:
            item = get_or_404(session, resource.model, pk, resource.label)
            return respond(resource.response_schema, item)

    def update_item(pk: int) -> ResponseReturnValue:
        """Apply a partial update to one item."""
        payload = resource.update_schema.model_validate(request.get_json())
        with get_session() as session:
            item = get_or_404(session, resource.model, pk, resource.label)
            apply_updates(item, payload)
            session.commit()
            session.refresh(item)
            return respond(resource.response_schema, item)

    def delete_item(pk: int) -> ResponseReturnValue:
        """Delete one item unless shots reference it (409)."""
        with get_session() as session:
            item = get_or_404(session, resource.model, pk, resource.label)
            ensure_no_shots_reference(
                session, resource.shot_column, pk, resource.conflict_noun
            )
            session.delete(item)
            session.commit()
            return "", HTTPStatus.NO_CONTENT

    blueprint.add_url_rule(rule, f"list_{resource.plural}", list_items, methods=["GET"])
    blueprint.add_url_rule(
        rule, f"create_{resource.singular}", create_item, methods=["POST"]
    )
    blueprint.add_url_rule(
        item_rule, f"get_{resource.singular}", get_item, methods=["GET"]
    )
    blueprint.add_url_rule(
        item_rule, f"update_{resource.singular}", update_item, methods=["PUT"]
    )
    blueprint.add_url_rule(
        item_rule, f"delete_{resource.singular}", delete_item, methods=["DELETE"]
    )
