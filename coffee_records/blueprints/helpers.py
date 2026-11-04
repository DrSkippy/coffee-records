"""Helpers shared by the API blueprints: config access, lookups, uploads, params."""

import logging
from collections.abc import Callable
from datetime import date
from http import HTTPStatus
from typing import Any, TypeVar, cast

from flask import current_app, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import InstrumentedAttribute, Session
from werkzeug.datastructures import FileStorage

from coffee_records.config import Config
from coffee_records.database import Base
from coffee_records.errors import BadRequestError, ConflictError, NotFoundError
from coffee_records.models.shot import Shot
from coffee_records.services.storage import MediaStorage

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=Base)
DeleteFn = Callable[[str], None]


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


def delete_stored_file(filename: str, delete_fn: DeleteFn) -> None:
    """Delete a stored media file after a successful commit, logging failures.

    The owning database row is already committed at this point, so a file
    deletion failure must not turn a successful request into a 500.

    Args:
        filename: Stored filename to remove.
        delete_fn: Storage deletion callable (e.g. ``MediaStorage.delete``).
    """
    try:
        delete_fn(filename)
    except OSError:
        logger.warning(
            "Stored media file %r could not be deleted; orphaned on disk",
            filename,
            exc_info=True,
        )


def replace_media(
    session: Session,
    instance: Base,
    attr: str,
    new_filename: str,
    delete_fn: DeleteFn,
) -> None:
    """Point a media attribute at a newly stored file and commit.

    The new file is removed again if the commit fails, so the row never
    references an untracked file; after a successful commit the replaced
    file is deleted (failures logged, never raised).

    Args:
        session: Active session to commit through.
        instance: ORM instance owning the media column.
        attr: Media filename attribute (e.g. ``"video_filename"``).
        new_filename: Newly stored filename to reference.
        delete_fn: Storage deletion callable for this media kind.

    Raises:
        SQLAlchemyError: If the commit fails (the new file is removed).
    """
    previous = cast("str | None", getattr(instance, attr))
    setattr(instance, attr, new_filename)
    try:
        session.commit()
    except SQLAlchemyError:
        delete_fn(new_filename)
        raise
    if previous:
        delete_stored_file(previous, delete_fn)


def clear_media(
    session: Session, instance: Base, attr: str, delete_fn: DeleteFn
) -> bool:
    """Clear a media attribute and delete the file it referenced.

    Nothing happens when the attribute is already empty. The deletion
    happens after the commit; failures are logged, never raised.

    Args:
        session: Active session to commit through.
        instance: ORM instance owning the media column.
        attr: Media filename attribute (e.g. ``"image_filename"``).
        delete_fn: Storage deletion callable for this media kind.

    Returns:
        True when a file was cleared, False when the attribute was empty.

    Raises:
        SQLAlchemyError: If the commit fails.
    """
    previous = cast("str | None", getattr(instance, attr))
    if not previous:
        return False
    setattr(instance, attr, None)
    session.commit()
    delete_stored_file(previous, delete_fn)
    return True
