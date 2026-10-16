"""Helpers shared by the API blueprints: config access, lookups, uploads, params."""

from datetime import date
from http import HTTPStatus
from typing import Any, TypeVar, cast

from flask import current_app, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import BaseModel
from sqlalchemy.orm import InstrumentedAttribute, Session
from werkzeug.datastructures import FileStorage

from coffee_records.config import Config
from coffee_records.database import Base
from coffee_records.errors import BadRequestError, ConflictError, NotFoundError
from coffee_records.models.shot import Shot
from coffee_records.services.storage import MediaStorage

ModelT = TypeVar("ModelT", bound=Base)


def get_config() -> Config:
    """Return the application config attached to the current Flask app.

    Returns:
        The app's Config.
    """
    return cast(Config, current_app.config["APP_CONFIG"])


def get_storage() -> MediaStorage:
    """Return a MediaStorage rooted at the configured media directory.

    Returns:
        MediaStorage for uploads.
    """
    return MediaStorage(get_config().uploads.media_dir)


def get_or_404(session: Session, model: type[ModelT], pk: int, label: str) -> ModelT:
    """Load a row by primary key or raise NotFoundError.

    Args:
        session: Active session.
        model: ORM model class.
        pk: Primary key value.
        label: Human name for the error message (e.g. "Coffee").

    Returns:
        The loaded instance.

    Raises:
        NotFoundError: If no row exists.
    """
    instance = session.get(model, pk)
    if instance is None:
        raise NotFoundError(f"{label} not found")
    return instance


def apply_updates(instance: Base, payload: BaseModel) -> None:
    """Copy every non-None field of an update payload onto an ORM instance.

    Args:
        instance: ORM instance to mutate.
        payload: Partial-update Pydantic model.
    """
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(instance, field, value)


def ensure_no_shots_reference(
    session: Session, column: InstrumentedAttribute[Any], pk: int, noun: str
) -> None:
    """Raise ConflictError if any shot references the row.

    Args:
        session: Active session.
        column: Shot foreign-key column (e.g. ``Shot.grinder_id``).
        pk: Referenced primary key.
        noun: Word used in the message (e.g. "grinder").

    Raises:
        ConflictError: If one or more shots reference the row.
    """
    count = session.query(Shot).filter(column == pk).count()
    if count > 0:
        raise ConflictError(f"Cannot delete: {count} shot(s) reference this {noun}")


def respond(
    schema: type[BaseModel], instance: object, status: int = HTTPStatus.OK
) -> ResponseReturnValue:
    """Serialize an ORM instance through a response schema.

    Args:
        schema: Pydantic response model with ``from_attributes`` enabled.
        instance: ORM instance.
        status: HTTP status code.

    Returns:
        Flask JSON response tuple.
    """
    return jsonify(schema.model_validate(instance).model_dump(mode="json")), status


def require_upload() -> FileStorage:
    """Return the uploaded ``file`` part of a multipart request.

    Returns:
        The uploaded file.

    Raises:
        BadRequestError: If no file or an empty filename was sent.
    """
    if "file" not in request.files:
        raise BadRequestError("No file provided")
    upload = request.files["file"]
    if not upload.filename:
        raise BadRequestError("Empty filename")
    return upload


def query_int(name: str) -> int | None:
    """Parse an optional integer query parameter.

    Args:
        name: Query parameter name.

    Returns:
        The integer, or None when absent or empty.

    Raises:
        BadRequestError: If the value is not an integer.
    """
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise BadRequestError(f"{name} must be an integer") from None


def require_query_int(name: str) -> int:
    """Parse a required integer query parameter.

    Args:
        name: Query parameter name.

    Returns:
        The integer value.

    Raises:
        BadRequestError: If missing or not an integer.
    """
    value = query_int(name)
    if value is None:
        raise BadRequestError(f"{name} required")
    return value


def query_date(name: str) -> date | None:
    """Parse an optional ISO date query parameter.

    Args:
        name: Query parameter name.

    Returns:
        The date, or None when absent or empty.

    Raises:
        BadRequestError: If the value is not an ISO date.
    """
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise BadRequestError(f"{name} must be an ISO date (YYYY-MM-DD)") from None
