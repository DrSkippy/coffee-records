"""Health check blueprint."""

from importlib.metadata import version as pkg_version

from flask import Blueprint, jsonify
from sqlalchemy import text

from coffee_records.database import get_session

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> object:
    """Return service health status.

    Returns:
        JSON with status and database connectivity.
    """
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return jsonify({"status": "ok", "database": db_status})


@health_bp.get("/api/version")
def api_version() -> object:
    """Return the API version.

    Returns:
        JSON with the current API version string.
    """
    return jsonify({"version": pkg_version("coffee-records")})
