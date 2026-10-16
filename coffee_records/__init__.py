"""Coffee Records Flask application factory."""

import hmac
import logging.config
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

from coffee_records.config import Config, load_config
from coffee_records.database import init_db
from coffee_records.errors import register_error_handlers

API_KEY_HEADER = "X-API-Key"


class ConfigurationError(RuntimeError):
    """Raised when the application is started with unsafe or missing settings."""


def _require_secret_key(config: Config) -> None:
    """Refuse to run outside debug mode without a SECRET_KEY.

    Args:
        config: Loaded application config.

    Raises:
        ConfigurationError: If no secret key is configured and debug is off.
    """
    if not config.app.secret_key and not config.app.debug:
        raise ConfigurationError(
            "SECRET_KEY environment variable must be set when debug is disabled"
        )


def _api_key_is_valid(provided: str | None, required: str) -> bool:
    """Compare API keys in constant time.

    Args:
        provided: Key sent by the client, if any.
        required: Configured key.

    Returns:
        True when the keys match.
    """
    return provided is not None and hmac.compare_digest(
        provided.encode(), required.encode()
    )


def create_app(config: Config | None = None, database_url: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Optional Config override (used in tests).
        database_url: Optional database URL override (used in tests).

    Returns:
        Configured Flask application instance.

    Raises:
        ConfigurationError: If SECRET_KEY is missing outside debug mode.
    """
    if config is None:
        config = load_config()
    _require_secret_key(config)

    logging.config.dictConfig(config.logging.to_dict_config())

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["SECRET_KEY"] = config.app.secret_key
    app.config["DEBUG"] = config.app.debug
    app.config["APP_CONFIG"] = config

    # Initialize database
    url = database_url if database_url is not None else config.database.get_url()
    init_db(url, pool_size=config.database.pool_size)

    # API key authentication for all /api/* routes
    @app.before_request
    def check_api_key() -> ResponseReturnValue | None:
        """Enforce the X-API-Key header on /api/* routes when api_key is configured."""
        required_key = config.app.api_key
        if not request.path.startswith("/api/") or not required_key:
            return None
        if not _api_key_is_valid(request.headers.get(API_KEY_HEADER), required_key):
            return jsonify({"error": "Unauthorized"}), 401
        return None

    # Register global error handlers
    register_error_handlers(app)

    # Register blueprints
    from coffee_records.blueprints.coffees import coffees_bp
    from coffee_records.blueprints.defaults import defaults_bp
    from coffee_records.blueprints.equipment import equipment_bp
    from coffee_records.blueprints.health import health_bp
    from coffee_records.blueprints.reports import reports_bp
    from coffee_records.blueprints.shots import shots_bp

    for blueprint in (
        health_bp,
        coffees_bp,
        defaults_bp,
        equipment_bp,
        shots_bp,
        reports_bp,
    ):
        app.register_blueprint(blueprint)

    # Serve React SPA for all non-API routes
    static_dir = Path(__file__).parent / "static"

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path: str) -> ResponseReturnValue:
        """Serve the React SPA or static assets.

        Args:
            path: URL path segment.

        Returns:
            Static file or index.html for SPA routing.
        """
        if path and (static_dir / path).exists():
            return send_from_directory(str(static_dir), path)
        return send_from_directory(str(static_dir), "index.html")

    return app
