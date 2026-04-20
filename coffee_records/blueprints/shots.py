"""Shots blueprint — /api/shots."""

import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.orm import joinedload
from werkzeug.datastructures import FileStorage

from coffee_records.config import Config
from coffee_records.database import get_session
from coffee_records.models.shot import Shot
from coffee_records.schemas.shot import ShotCreate, ShotResponse, ShotUpdate

shots_bp = Blueprint("shots", __name__, url_prefix="/api/shots")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
ALLOWED_TELEMETRY_EXTENSIONS = {".json"}


def _cfg() -> Config:
    """Return the application config."""
    return current_app.config["APP_CONFIG"]  # type: ignore[return-value]


def _save_video(file: FileStorage, cfg: Config) -> str:
    """Save an uploaded video and return its filename.

    Args:
        file: The uploaded file object.
        cfg: Application config.

    Returns:
        The saved filename (UUID-based).
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        ext = ".mp4"
    filename = f"{uuid.uuid4()}{ext}"
    dest = Path(cfg.uploads.coffee_image_dir)
    dest.mkdir(parents=True, exist_ok=True)
    file.save(dest / filename)
    return filename


def _delete_video_file(filename: str, cfg: Config) -> None:
    """Delete a video file from disk if it exists.

    Args:
        filename: The filename to delete.
        cfg: Application config.
    """
    path = Path(cfg.uploads.coffee_image_dir) / filename
    if path.exists():
        path.unlink()


def _save_telemetry(file: FileStorage, cfg: Config) -> str:
    """Save an uploaded telemetry JSON and return its filename.

    Args:
        file: The uploaded file object.
        cfg: Application config.

    Returns:
        The saved filename (UUID-based).
    """
    filename = f"{uuid.uuid4()}.json"
    dest = Path(cfg.uploads.coffee_image_dir) / "telemetry"
    dest.mkdir(parents=True, exist_ok=True)
    file.save(dest / filename)
    return filename


def _delete_telemetry_file(filename: str, cfg: Config) -> None:
    """Delete a telemetry file from disk if it exists.

    Args:
        filename: The filename to delete.
        cfg: Application config.
    """
    path = Path(cfg.uploads.coffee_image_dir) / "telemetry" / filename
    if path.exists():
        path.unlink()


def _load_shot(session: object, shot_id: int) -> Shot | None:
    """Load a Shot with all relationships eagerly.

    Args:
        session: SQLAlchemy session.
        shot_id: The shot primary key.

    Returns:
        Shot instance with relationships loaded, or None.
    """
    from sqlalchemy.orm import Session

    s: Session = session  # type: ignore[assignment]
    return (
        s.query(Shot)
        .options(
            joinedload(Shot.coffee),
            joinedload(Shot.grinder),
            joinedload(Shot.device),
            joinedload(Shot.scale),
        )
        .filter(Shot.id == shot_id)
        .first()
    )


@shots_bp.get("")
def list_shots() -> object:
    """List shots with optional filters.

    Query params: maker, coffee_id, date_from (ISO), date_to (ISO), limit, offset.

    Returns:
        JSON array of ShotResponse objects.
    """
    maker = request.args.get("maker")
    coffee_id = request.args.get("coffee_id", type=int)
    date_from_str = request.args.get("date_from")
    date_to_str = request.args.get("date_to")
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", default=0, type=int)

    with get_session() as session:
        q = session.query(Shot).options(
            joinedload(Shot.coffee),
            joinedload(Shot.grinder),
            joinedload(Shot.device),
            joinedload(Shot.scale),
        )
        if maker:
            q = q.filter(Shot.maker == maker)
        if coffee_id is not None:
            q = q.filter(Shot.coffee_id == coffee_id)
        if date_from_str:
            q = q.filter(Shot.date >= date.fromisoformat(date_from_str))
        if date_to_str:
            q = q.filter(Shot.date <= date.fromisoformat(date_to_str))
        q = q.order_by(Shot.date.desc(), Shot.created_at.desc())
        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(limit)
        shots = q.all()
        return jsonify([ShotResponse.from_orm_shot(s).model_dump(mode="json") for s in shots])


@shots_bp.post("")
def create_shot() -> object:
    """Create a new shot.

    Returns:
        JSON ShotResponse with 201 status.
    """
    payload = ShotCreate.model_validate(request.get_json())
    with get_session() as session:
        shot = Shot(**payload.model_dump())
        session.add(shot)
        session.commit()
        # reload with relationships
        loaded = _load_shot(session, shot.id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json")), 201


@shots_bp.get("/<int:shot_id>")
def get_shot(shot_id: int) -> object:
    """Get a single shot by ID.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON ShotResponse or 404.
    """
    with get_session() as session:
        shot = _load_shot(session, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        return jsonify(ShotResponse.from_orm_shot(shot).model_dump(mode="json"))


@shots_bp.put("/<int:shot_id>")
def update_shot(shot_id: int) -> object:
    """Update a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    payload = ShotUpdate.model_validate(request.get_json())
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(shot, field, value)
        session.commit()
        loaded = _load_shot(session, shot_id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json"))


@shots_bp.delete("/<int:shot_id>")
def delete_shot(shot_id: int) -> object:
    """Delete a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        204 on success, 404 if not found.
    """
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        if shot.video_filename:
            _delete_video_file(shot.video_filename, _cfg())
        if shot.telemetry_filename:
            _delete_telemetry_file(shot.telemetry_filename, _cfg())
        session.delete(shot)
        session.commit()
        return "", 204


@shots_bp.post("/<int:shot_id>/video")
def upload_shot_video(shot_id: int) -> object:
    """Upload a video for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 400/404.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    cfg = _cfg()
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        if shot.video_filename:
            _delete_video_file(shot.video_filename, cfg)
        shot.video_filename = _save_video(file, cfg)
        session.commit()
        loaded = _load_shot(session, shot_id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json"))


@shots_bp.delete("/<int:shot_id>/video")
def delete_shot_video(shot_id: int) -> object:
    """Remove the video for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    cfg = _cfg()
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        if shot.video_filename:
            _delete_video_file(shot.video_filename, cfg)
            shot.video_filename = None
            session.commit()
        loaded = _load_shot(session, shot_id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json"))


@shots_bp.post("/<int:shot_id>/telemetry")
def upload_shot_telemetry(shot_id: int) -> object:
    """Upload a telemetry JSON for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 400/404.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    cfg = _cfg()
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        if shot.telemetry_filename:
            _delete_telemetry_file(shot.telemetry_filename, cfg)
        shot.telemetry_filename = _save_telemetry(file, cfg)
        session.commit()
        loaded = _load_shot(session, shot_id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json"))


@shots_bp.delete("/<int:shot_id>/telemetry")
def delete_shot_telemetry(shot_id: int) -> object:
    """Remove the telemetry file for a shot.

    Args:
        shot_id: Shot primary key.

    Returns:
        JSON updated ShotResponse or 404.
    """
    cfg = _cfg()
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return jsonify({"error": "Shot not found"}), 404
        if shot.telemetry_filename:
            _delete_telemetry_file(shot.telemetry_filename, cfg)
            shot.telemetry_filename = None
            session.commit()
        loaded = _load_shot(session, shot_id)
        assert loaded is not None
        return jsonify(ShotResponse.from_orm_shot(loaded).model_dump(mode="json"))
