"""Coffee Records Flask application factory."""

import logging
import logging.config
from pathlib import Path

from flask import Flask, send_from_directory

from coffee_records.config import Config, load_config
from coffee_records.database import init_db


def create_app(
    config: Config | None = None, database_url: str | None = None
) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Optional Config override (used in tests).
        database_url: Optional database URL override (used in tests).

    Returns:
        Configured Flask application instance.
    """
    if config is None:
        config = load_config()

    logging.basicConfig(level=getattr(logging, config.logging.level, logging.INFO))

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["SECRET_KEY"] = config.app.secret_key
    app.config["DEBUG"] = config.app.debug

    # Initialize database
    url = database_url if database_url is not None else config.database.get_url()
    init_db(url, pool_size=config.database.pool_size)

    # Register global error handlers
    from pydantic import ValidationError

    @app.errorhandler(ValidationError)
    def handle_validation_error(exc: ValidationError) -> object:
        """Return 422 for Pydantic validation failures."""
        return {"errors": exc.errors()}, 422

    # Register blueprints
    from coffee_records.blueprints.coffees import coffees_bp
    from coffee_records.blueprints.equipment import equipment_bp
    from coffee_records.blueprints.health import health_bp
    from coffee_records.blueprints.reports import reports_bp
    from coffee_records.blueprints.shots import shots_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(coffees_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(shots_bp)
    app.register_blueprint(reports_bp)

    # Serve React SPA for all non-API routes
    static_dir = Path(__file__).parent / "static"

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path: str) -> object:
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
