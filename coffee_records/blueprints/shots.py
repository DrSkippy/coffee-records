"""Shots blueprint — /api/shots."""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from coffee_records.blueprints.helpers import (
    apply_updates,
    get_config,
    get_or_404,
    get_storage,
    query_date,
    query_int,
    require_query_int,
    require_upload,
)
from coffee_records.database import get_session
from coffee_records.errors import NotFoundError, UnprocessableError
from coffee_records.models.equipment import Grinder
from coffee_records.models.shot import Shot
from coffee_records.schemas.shot import (
    LastGrindResponse,
    ShotCreate,
    ShotResponse,
    ShotUpdate,
)
from coffee_records.services.brewmeo_import import (
    BrewmeoImportError,
    build_import,
    parse_brewmeo_csv,
)
from coffee_records.services.grind_validation import validate_grind_setting
from coffee_records.services.last_grind import find_last_grind_shot
from coffee_records.services.storage import VIDEO_EXTENSIONS
from coffee_records.services.telemetry import (
    TelemetryValidationError,
    render_telemetry_thumbnail,
)

shots_bp = Blueprint("shots", __name__, url_prefix="/api/shots")

DEFAULT_VIDEO_EXTENSION = ".mp4"
_SHOT_RELATIONSHIPS = (
    joinedload(Shot.coffee),
    joinedload(Shot.grinder),
    joinedload(Shot.device),
    joinedload(Shot.scale),
)


def _load_shot(session: Session, shot_id: int) -> Shot | None:
    """Load a Shot with all relationships eagerly.

    Args:
        session: SQLAlchemy session.
        shot_id: The shot primary key.

    Returns:
        Shot instance with relationships loaded, or None.
    """
    return (
        session.query(Shot)
        .options(*_SHOT_RELATIONSHIPS)
        .filter(Shot.id == shot_id)
        .first()
    )


def _shot_response(
    session: Session, shot_id: int, status: int = HTTPStatus.OK
) -> ResponseReturnValue:
    """Reload a shot with relationships and serialize it.

    Args:
        session: SQLAlchemy session.
        shot_id: The shot primary key.
        status: HTTP status code.

    Returns:
        JSON ShotResponse.

    Raises:
        NotFoundError: If the shot does not exist.
    """
    shot = _load_shot(session, shot_id)
    if shot is None:
        raise NotFoundError("Shot not found")
    return jsonify(ShotResponse.from_orm_shot(shot).model_dump(mode="json")), status


def _check_grind_setting(
    session: Session, grind_setting: str | None, grinder_id: int | None
) -> None:
    """Validate a grind setting's notation against its grinder.

    Args:
        session: SQLAlchemy session.
        grind_setting: Setting to validate (skipped when empty).
        grinder_id: Grinder the setting applies to (skipped when None/unknown).

    Raises:
        UnprocessableError: If the notation does not fit the grinder.
    """
    if not grind_setting or grinder_id is None:
        return
    grinder = session.get(Grinder, grinder_id)
    if grinder is None:
        return
    error = validate_grind_setting(
        grind_setting, grinder.make, grinder.model, get_config().grinders
    )
    if error:
        raise UnprocessableError(error)


@shots_bp.get("/makers")
def list_makers() -> ResponseReturnValue:
    """List every distinct maker that has logged a shot.

    Returns:
        JSON array of maker names, sorted case-insensitively.
    """
    with get_session() as session:
        rows = session.query(Shot.maker).distinct().all()
    makers = sorted({name for (name,) in rows if name}, key=str.casefold)
    return jsonify(makers)


@shots_bp.get("/last-grind")
def last_grind() -> ResponseReturnValue:
    """Return the most recent grind setting recorded for a coffee.

    Used to default the New Shot form's grind setting. The first shot of a
    coffee has no history, so every field except coffee_id/grinder_id is null.

    Query params:
        coffee_id (required): Coffee bag.
        grinder_id (optional): Only consider shots on this grinder.

    Returns:
        JSON LastGrindResponse.
    """
    coffee_id = require_query_int("coffee_id")
    grinder_id = query_int("grinder_id")
    with get_session() as session:
        shot = find_last_grind_shot(session, coffee_id, grinder_id)
        response = LastGrindResponse(
            coffee_id=coffee_id,
            grinder_id=grinder_id,
            grind_setting=shot.grind_setting if shot else None,
            shot_id=shot.id if shot else None,
            date=shot.date if shot else None,
        )
    return jsonify(response.model_dump(mode="json"))


@shots_bp.get("")
def list_shots() -> ResponseReturnValue:
    """List shots with optional filters.

    Query params: maker, coffee_id, date_from (ISO), date_to (ISO), limit, offset.

    Returns:
        JSON array of ShotResponse objects.
    """
    maker = request.args.get("maker")
    coffee_id = query_int("coffee_id")
    date_from = query_date("date_from")
    date_to = query_date("date_to")
    limit = query_int("limit")
    offset = query_int("offset")

    with get_session() as session:
        q = session.query(Shot).options(*_SHOT_RELATIONSHIPS)
        if maker:
            q = q.filter(Shot.maker == maker)
        if coffee_id is not None:
            q = q.filter(Shot.coffee_id == coffee_id)
        if date_from:
            q = q.filter(Shot.date >= date_from)
        if date_to:
            q = q.filter(Shot.date <= date_to)
        q = q.order_by(Shot.date.desc(), Shot.created_at.desc())
        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(limit)
        shots = q.all()
        return jsonify(
            [ShotResponse.from_orm_shot(s).model_dump(mode="json") for s in shots]
        )


@shots_bp.post("")
def create_shot() -> ResponseReturnValue:
    """Create a new shot.

    Returns:
        JSON ShotResponse with 201 status.
    """
    payload = ShotCreate.model_validate(request.get_json())
    with get_session() as session:
        _check_grind_setting(session, payload.grind_setting, payload.grinder_id)
        shot = Shot(**payload.model_dump())
        session.add(shot)
        session.commit()
        # reload with relationships
        return _shot_response(session, shot.id, HTTPStatus.CREATED)


@shots_bp.post("/import-csv")
def import_shot_csv() -> ResponseReturnValue:
    """Parse a Brewmeo shot CSV into New Shot form values and telemetry.

    The CSV is read in memory and discarded; nothing is written to the
    database or disk. The client creates the shot (and any proposed new
    coffee) and uploads the returned telemetry on save.

    Returns:
        JSON ShotCsvImportResponse, or 400/422 on a missing or invalid file.
    """
    upload = require_upload()
    try:
        text = upload.read().decode("utf-8-sig")
        shot = parse_brewmeo_csv(text)
    except UnicodeDecodeError:
        raise UnprocessableError("CSV must be UTF-8 text") from None
    except BrewmeoImportError as exc:
        raise UnprocessableError(str(exc)) from exc
    config = get_config()
    with get_session() as session:
        result = build_import(
            session,
            shot,
            upload.filename or "",
            brewmeo=config.brewmeo,
            matching=config.matching,
        )
    return jsonify(result.model_dump(mode="json"))


@shots_bp.get("/<int:shot_id>")
def get_shot(shot_id: int) -> ResponseReturnValue:
    """Get a single shot by ID.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON ShotResponse or 404.
    """
    with get_session() as session:
        return _shot_response(session, shot_id)


@shots_bp.put("/<int:shot_id>")
def update_shot(shot_id: int) -> ResponseReturnValue:
    """Update a shot.

    The grind setting is only re-validated when it changes, against the
    payload's grinder if given, else the shot's current grinder.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    payload = ShotUpdate.model_validate(request.get_json())
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        if payload.grind_setting != shot.grind_setting:
            effective_grinder_id = (
                payload.grinder_id
                if payload.grinder_id is not None
                else shot.grinder_id
            )
            _check_grind_setting(session, payload.grind_setting, effective_grinder_id)
        apply_updates(shot, payload)
        session.commit()
        return _shot_response(session, shot_id)


@shots_bp.delete("/<int:shot_id>")
def delete_shot(shot_id: int) -> ResponseReturnValue:
    """Delete a shot and, after the commit succeeds, its media files.

    Args:
        shot_id: Shot primary key.

    Returns:
        204 on success, 404 if not found.
    """
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        video, telemetry = shot.video_filename, shot.telemetry_filename
        session.delete(shot)
        session.commit()
    storage = get_storage()
    if video:
        storage.delete(video)
    if telemetry:
        storage.delete_telemetry(telemetry)
    return "", HTTPStatus.NO_CONTENT


@shots_bp.post("/<int:shot_id>/video")
def upload_shot_video(shot_id: int) -> ResponseReturnValue:
    """Upload a video for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 400/404.
    """
    upload = require_upload()
    storage = get_storage()
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        previous = shot.video_filename
        new_filename = storage.save_upload(
            upload, VIDEO_EXTENSIONS, DEFAULT_VIDEO_EXTENSION
        )
        shot.video_filename = new_filename
        try:
            session.commit()
        except SQLAlchemyError:
            storage.delete(new_filename)
            raise
        if previous:
            storage.delete(previous)
        return _shot_response(session, shot_id)


@shots_bp.delete("/<int:shot_id>/video")
def delete_shot_video(shot_id: int) -> ResponseReturnValue:
    """Remove the video for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        previous = shot.video_filename
        if previous:
            shot.video_filename = None
            session.commit()
            get_storage().delete(previous)
        return _shot_response(session, shot_id)


@shots_bp.post("/<int:shot_id>/telemetry")
def upload_shot_telemetry(shot_id: int) -> ResponseReturnValue:
    """Upload a telemetry JSON for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 400/404/422.
    """
    upload = require_upload()
    payload = upload.read()
    try:
        thumbnail = render_telemetry_thumbnail(payload)
    except TelemetryValidationError as exc:
        raise UnprocessableError(str(exc)) from exc
    storage = get_storage()
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        previous = shot.telemetry_filename
        new_filename = storage.save_telemetry(payload, thumbnail)
        shot.telemetry_filename = new_filename
        try:
            session.commit()
        except SQLAlchemyError:
            storage.delete_telemetry(new_filename)
            raise
        if previous:
            storage.delete_telemetry(previous)
        return _shot_response(session, shot_id)


@shots_bp.delete("/<int:shot_id>/telemetry")
def delete_shot_telemetry(shot_id: int) -> ResponseReturnValue:
    """Remove the telemetry file for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    with get_session() as session:
        shot = get_or_404(session, Shot, shot_id, "Shot")
        previous = shot.telemetry_filename
        if previous:
            shot.telemetry_filename = None
            session.commit()
            get_storage().delete_telemetry(previous)
        return _shot_response(session, shot_id)
