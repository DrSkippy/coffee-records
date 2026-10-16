"""Tests for configuration loading, environment overrides and startup guards."""

from pathlib import Path

import pytest

from coffee_records import ConfigurationError, _api_key_is_valid, create_app
from coffee_records.config import AppConfig, Config, UploadsConfig, load_config
from coffee_records.models.shot import DrinkType


def test_load_config_reads_yaml_and_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibration blocks in config.yaml populate typed settings."""
    for name in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(
        "database:\n  host: db.local\n"
        "grind_model:\n  reference_temp_f: 70.0\n  espresso_drink_types: [latte]\n"
    )
    config = load_config(path)
    assert config.database.host == "db.local"
    assert config.grind_model.reference_temp_f == 70.0
    assert config.grind_model.espresso_drink_types == [DrinkType.latte]
    # Untouched sections keep their defaults
    assert config.reports.default_range_days == 30


def test_environment_overrides_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Secrets and database location come from the environment."""
    path = tmp_path / "config.yaml"
    path.write_text("database:\n  host: from-yaml\n  name: yaml-db\n")
    monkeypatch.setenv("POSTGRES_HOST", "from-env")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DATABASE", "env-db")
    monkeypatch.setenv("SECRET_KEY", "s3cret")
    monkeypatch.setenv("API_KEY", "k")
    config = load_config(path)
    assert config.database.host == "from-env"
    assert config.database.port == 6543
    assert config.database.name == "env-db"
    assert config.app.secret_key == "s3cret"
    assert config.app.api_key == "k"


def test_missing_config_file_uses_defaults(tmp_path: Path) -> None:
    """A missing config.yaml yields default settings."""
    config = load_config(tmp_path / "absent.yaml")
    assert config.server.workers == 4


def test_legacy_coffee_image_dir_key_still_accepted() -> None:
    """The old uploads.coffee_image_dir key maps onto media_dir."""
    uploads = UploadsConfig.model_validate({"coffee_image_dir": "/old"})
    assert uploads.media_dir == "/old"


def test_database_url_uses_env_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials are taken from the environment, never config."""
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    url = Config().database.get_url()
    assert url.startswith("postgresql+psycopg2://u:p@")


def test_logging_dict_config_shape() -> None:
    """Logging settings render to a valid dictConfig mapping."""
    dict_config = Config().logging.to_dict_config()
    assert dict_config["root"]["level"] == "INFO"
    assert dict_config["version"] == 1


def test_create_app_requires_secret_key_outside_debug() -> None:
    """Production mode refuses to start without a secret key."""
    with pytest.raises(ConfigurationError):
        create_app(config=Config(app=AppConfig(debug=False, secret_key="")))


@pytest.mark.parametrize(
    ("provided", "expected"),
    [("abc", True), ("abd", False), (None, False), ("", False)],
)
def test_api_key_comparison(provided: str | None, expected: bool) -> None:
    """API keys are compared exactly (and in constant time)."""
    assert _api_key_is_valid(provided, "abc") is expected
