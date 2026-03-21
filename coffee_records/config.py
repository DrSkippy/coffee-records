"""Application configuration loaded from config.yaml and environment variables."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class AppConfig(BaseModel):
    """Application settings."""

    debug: bool = False
    secret_key: str = "changeme"


class DatabaseConfig(BaseModel):
    """Database connection settings."""

    host: str = "192.168.1.91"
    port: int = 5434
    name: str = "coffee-records"
    pool_size: int = 5

    def get_url(self) -> str:
        """Build SQLAlchemy database URL from config and environment."""
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        return f"postgresql+psycopg2://{user}:{password}@{self.host}:{self.port}/{self.name}"


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: str = "INFO"


class ServerConfig(BaseModel):
    """Server settings."""

    host: str = "0.0.0.0"
    port: int = 5000
    workers: int = 4


class UploadsConfig(BaseModel):
    """File upload settings."""

    coffee_image_dir: str = "/var/www/html/resources/coffee"
    coffee_image_base_url: str = "https://resources.drskippy.app/coffee"


class Config(BaseModel):
    """Root configuration object."""

    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    server: ServerConfig = ServerConfig()
    uploads: UploadsConfig = UploadsConfig()


def load_config(path: Path | None = None) -> Config:
    """Load configuration from a YAML file.

    Args:
        path: Path to config.yaml. Defaults to project root config.yaml.

    Returns:
        Populated Config object.
    """
    if path is None:
        path = Path(__file__).parent.parent / "config.yaml"
    raw: dict[str, Any] = {}
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    return Config(**raw)
