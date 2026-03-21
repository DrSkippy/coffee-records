"""Health check blueprint."""

import tomllib
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, jsonify
from sqlalchemy import text

from coffee_records.database import get_session

health_bp = Blueprint("health", __name__)


@lru_cache(maxsize=1)
def _read_version() -> str:
    """Read the package version from pyproject.toml.

    Returns:
        Version string from [tool.poetry] section.
    """
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return str(data["tool"]["poetry"]["version"])


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
    return jsonify({"version": _read_version()})
