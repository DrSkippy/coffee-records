"""Application configuration loaded from config.yaml and environment variables.

Non-secret settings, including every model calibration constant, live in
``config.yaml``. Secrets and deployment-specific overrides come only from the
environment (see ``EnvOverrides``), loaded via direnv locally and Docker
Compose in production.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from coffee_records.models.shot import DrinkType

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


class AppConfig(BaseModel):
    """Application settings.

    ``secret_key`` and ``api_key`` are populated from the ``SECRET_KEY`` and
    ``API_KEY`` environment variables, never from config.yaml.
    """

    debug: bool = False
    secret_key: str = ""
    api_key: str = ""


class DatabaseConfig(BaseModel):
    """Database connection settings."""

    host: str = "localhost"
    port: int = 5432
    name: str = "coffee-records"
    pool_size: int = 5

    def get_url(self) -> str:
        """Build the SQLAlchemy database URL from config and environment.

        Returns:
            A ``postgresql+psycopg2`` URL including credentials.

        Raises:
            KeyError: If ``POSTGRES_USER`` or ``POSTGRES_PASSWORD`` is unset.
        """
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        return f"postgresql+psycopg2://{user}:{password}@{self.host}:{self.port}/{self.name}"


class LoggingConfig(BaseModel):
    """Logging settings, applied via ``logging.config.dictConfig``."""

    level: str = "INFO"
    format: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    def to_dict_config(self) -> dict[str, Any]:
        """Return a ``logging.config.dictConfig`` mapping for these settings.

        Returns:
            A dictConfig-compatible dict with one stream handler on the root logger.
        """
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": self.format}},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"}
            },
            "root": {"level": self.level, "handlers": ["console"]},
        }


class ServerConfig(BaseModel):
    """Gunicorn server settings (read by gunicorn.conf.py)."""

    host: str = "0.0.0.0"
    port: int = 5000
    workers: int = 4


class UploadsConfig(BaseModel):
    """File upload settings."""

    media_dir: str = Field(
        default="/var/www/html/resources/coffee",
        validation_alias=AliasChoices("media_dir", "coffee_image_dir"),
    )
    coffee_image_base_url: str = "https://resources.drskippy.app/coffee"


class ReportsConfig(BaseModel):
    """Report query settings."""

    default_range_days: int = 30


class GrindModelConfig(BaseModel):
    """Calibration for grind regression and the multivariate grind model.

    Features are centered on these reference values, so coefficients describe
    the grind change per unit of deviation from a typical shot.
    """

    reference_temp_f: float = 65.0
    reference_dose_g: float = 20.0
    target_brew_ratio: float = 2.0
    min_within_coffee_range: float = 0.5
    min_points: int = 3
    espresso_drink_types: list[DrinkType] = [
        DrinkType.americano,
        DrinkType.latte,
        DrinkType.cappuccino,
    ]


class GrindersConfig(BaseModel):
    """How grinders are recognised from their make/model text."""

    dual_scale_keywords: list[str] = ["mazzer"]
    single_number_keywords: list[str] = ["option-o", "timemore", "baratza"]
    dual_scale_min_value: float = 30.0


class MatchingConfig(BaseModel):
    """Fuzzy-match thresholds for recognising an existing coffee bag."""

    coffee_name_threshold: float = 0.8
    roaster_threshold: float = 0.5
    token_overlap_threshold: float = 0.5
    equipment_min_overlap: float = 0.5


class BrewmeoConfig(BaseModel):
    """Signal-processing calibration for Brewmeo CSV imports."""

    flow_smoothing_tenths: int = 5
    flow_half_window_tenths: int = 5
    disturbance_grams: float = 5.0
    disturbance_seconds: float = 0.25
    disturbance_tail_fraction: float = 0.2
    final_weight_tolerance_grams: float = 2.0


class ShotDefaultsSeed(BaseModel):
    """Initial values for the New Shot form defaults singleton."""

    maker: str = "Scott"
    dose_weight: float | None = 20.0
    pre_infusion_time: str | None = "5+5"
    extraction_time: float | None = 28.0
    final_weight: float | None = 40.0
    drink_type: DrinkType | None = DrinkType.americano
    grinder_temp_before: float | None = 64.0
    wedge: bool = True
    shaker: bool = True
    wdt: bool = True
    flow_taper: bool = False


class Config(BaseModel):
    """Root configuration object."""

    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    server: ServerConfig = ServerConfig()
    uploads: UploadsConfig = UploadsConfig()
    reports: ReportsConfig = ReportsConfig()
    grind_model: GrindModelConfig = GrindModelConfig()
    grinders: GrindersConfig = GrindersConfig()
    matching: MatchingConfig = MatchingConfig()
    brewmeo: BrewmeoConfig = BrewmeoConfig()
    shot_defaults_seed: ShotDefaultsSeed = ShotDefaultsSeed()


class EnvOverrides(BaseSettings):
    """Secrets and deployment overrides read from the environment."""

    model_config = SettingsConfigDict(extra="ignore")

    secret_key: str | None = None
    api_key: str | None = None
    postgres_host: str | None = None
    postgres_port: int | None = None
    postgres_database: str | None = None

    def apply(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Merge the set environment values into a raw config mapping.

        Args:
            raw: Parsed config.yaml contents (mutated and returned).

        Returns:
            The same mapping with environment values taking priority.
        """
        targets: dict[str, tuple[str, str]] = {
            "secret_key": ("app", "secret_key"),
            "api_key": ("app", "api_key"),
            "postgres_host": ("database", "host"),
            "postgres_port": ("database", "port"),
            "postgres_database": ("database", "name"),
        }
        for field_name, (section, key) in targets.items():
            value = getattr(self, field_name)
            if value is not None:
                raw.setdefault(section, {})[key] = value
        return raw


def load_config(path: Path | None = None) -> Config:
    """Load configuration from a YAML file, then apply environment overrides.

    Args:
        path: Path to config.yaml. Defaults to the project root config.yaml.

    Returns:
        Populated Config object.
    """
    path = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open() as f:
            raw = yaml.safe_load(f) or {}
    return Config(**EnvOverrides().apply(raw))
