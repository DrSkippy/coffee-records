"""Unit tests for pure service helpers (no Flask app or database needed)."""

from datetime import date
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from werkzeug.datastructures import FileStorage

from coffee_records.config import GrindersConfig
from coffee_records.services.brew_time import format_brew_time, parse_brew_time
from coffee_records.services.grind_model.estimator import fit_within_coffee
from coffee_records.services.grind_notation import (
    GrinderFamily,
    classify_grinder,
    format_grind_numeric,
    parse_grind_numeric,
)
from coffee_records.services.grind_validation import validate_grind_setting
from coffee_records.services.matching import fuzzy_match, is_same_beans
from coffee_records.services.reports.filters import ShotFilter, equipment_label
from coffee_records.services.reports.regression import fit_bivariate
from coffee_records.services.reports.target_time import weighted_moving_average
from coffee_records.services.stats import r_squared
from coffee_records.services.storage import MediaStorage, thumbnail_name

# ── Grind notation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8+7 1/2", 87.5),
        ("8+71/2", 87.5),
        ("8+7½", 87.5),
        (" 8+5 ", 85.0),
        ("8+ 1/4", 80.25),
        ("8+7+1/2", 87.5),
        ("19.5", 19.5),
        ("7", 7.0),
        ("8+7 1/0", None),  # malformed fraction is unparseable, not silently 87
        ("8+7 a/b", None),
        ("x+7", None),
        ("8+y", None),
        ("fine", None),
    ],
)
def test_parse_grind_numeric(raw: str, expected: float | None) -> None:
    """Dual-scale, decimal and malformed settings parse as documented."""
    assert parse_grind_numeric(raw) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (87.5, "8+7 1/2"),
        (85.0, "8+5"),
        (84.9, "8+5"),  # fraction rounds up into the next fine step
        (80.25, "8+0 1/4"),
        (86.75, "8+6 3/4"),
        (19.5, "19.5"),
        (20.0, "20"),
        (12.345, "12.35"),
    ],
)
def test_format_grind_numeric(value: float, expected: str) -> None:
    """Numeric grind values render back into human notation."""
    assert format_grind_numeric(value) == expected


def test_format_grind_threshold_is_configurable() -> None:
    """The dual-scale threshold comes from configuration."""
    assert format_grind_numeric(25.0, GrindersConfig(dual_scale_min_value=20)) == "2+5"


@pytest.mark.parametrize(
    ("make", "model", "family"),
    [
        ("Mazzer", "Mini", GrinderFamily.DUAL_SCALE),
        ("Baratza", "Virtuoso+", GrinderFamily.SINGLE_NUMBER),
        ("Option-O", "Lagom P64", GrinderFamily.SINGLE_NUMBER),
        ("Niche", "Zero", None),
    ],
)
def test_classify_grinder(make: str, model: str, family: GrinderFamily | None) -> None:
    """Grinders are classified by configured keywords."""
    assert classify_grinder(make, model) is family


@pytest.mark.parametrize(
    ("setting", "make", "error"),
    [
        ("8+5 1/2", "Mazzer", False),
        ("8.5", "Mazzer", True),
        ("19.5", "Baratza", False),
        ("8+5", "Baratza", True),
        ("anything", "Niche", False),
    ],
)
def test_validate_grind_setting(setting: str, make: str, error: bool) -> None:
    """Notation errors are reported per grinder family."""
    assert (validate_grind_setting(setting, make, "X") is not None) is error


# ── Brew time ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "seconds"), [("0.10", 1.0), ("12.3", 12.3), ("7", 7.0), (4, 4.0)]
)
def test_parse_brew_time(raw: object, seconds: float) -> None:
    """S.T notation counts tenths after the dot."""
    assert parse_brew_time(raw) == pytest.approx(seconds)


@pytest.mark.parametrize("raw", ["inf", "a.b", "nan"])
def test_parse_brew_time_rejects_garbage(raw: str) -> None:
    """Malformed or non-finite values raise ValueError."""
    with pytest.raises(ValueError):
        parse_brew_time(raw)


def test_format_brew_time_round_trip() -> None:
    """Formatting rounds to tenths and parses back."""
    assert format_brew_time(37.908) == "37.9"
    assert format_brew_time(0.96) == "1.0"
    assert parse_brew_time(format_brew_time(12.34)) == pytest.approx(12.3)


# ── Matching ─────────────────────────────────────────────────────────────────


def test_is_same_beans_thresholds() -> None:
    """Names need a close match; roasters tolerate abbreviation; empty roaster matches."""
    assert is_same_beans("Ollancay", "Prodigal", "Ollancey", "Prodigal Coffee")
    assert is_same_beans("Kiangoi AB", None, "Kiangoi AB", "Queen City")
    assert not is_same_beans("Kiangoi", "Prodigal", "Ethiopia Guji", "Prodigal")
    assert not fuzzy_match("", "anything")


# ── Filters and statistics ───────────────────────────────────────────────────


def test_shot_filter_default_range() -> None:
    """Missing dates are filled with a trailing window ending today."""
    today = date(2026, 5, 31)
    resolved = ShotFilter(coffee_id=3).with_default_range(30, today=today)
    assert resolved.date_from == date(2026, 5, 1)
    assert resolved.date_to == today
    assert resolved.coffee_id == 3
    explicit = ShotFilter(date_from=date(2026, 1, 1)).with_default_range(30, today)
    assert explicit.date_from == date(2026, 1, 1)


def test_equipment_label() -> None:
    """Labels join make and model, or are None for missing equipment."""
    assert equipment_label("ECM", "Synchronika") == "ECM Synchronika"
    assert equipment_label(None, None) is None


def test_weighted_moving_average() -> None:
    """Recent values weigh more; empty input yields None."""
    assert weighted_moving_average([]) is None
    assert weighted_moving_average([10.0]) == 10.0
    # (1*10 + 2*20 + 3*30) / 6 = 23.33
    assert weighted_moving_average([10.0, 20.0, 30.0]) == 23.3


def test_r_squared_constant_series_is_none() -> None:
    """R² is undefined when y has no variance."""
    y = np.array([2.0, 2.0, 2.0])
    assert r_squared(y, y) is None
    assert r_squared(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0])) == 1.0


def test_fit_bivariate_recovers_coefficients() -> None:
    """Exact linear data recovers a, b, c with R² = 1."""
    x1 = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    x2 = np.array([1.0, -1.0, 0.5, 2.0, 0.0])
    y = 2.0 * x1 - 0.5 * x2 + 80.0
    fit = fit_bivariate(x1, x2, y)
    assert fit is not None
    assert (fit.a, fit.b, fit.c) == pytest.approx((2.0, -0.5, 80.0))
    assert fit.r_squared == 1.0


def test_fit_bivariate_singular_returns_none() -> None:
    """A constant regressor is collinear with the intercept."""
    x1 = np.array([0.0, 1.0, 2.0])
    x2 = np.array([3.0, 3.0, 3.0])
    assert fit_bivariate(x1, x2, np.array([1.0, 2.0, 3.0])) is None


def test_fit_within_coffee_recovers_effects() -> None:
    """Global slopes and per-group intercepts are recovered; flat features are zeroed."""
    rng = np.random.default_rng(0)
    n = 40
    groups = np.repeat([0, 1], n // 2)
    age = rng.uniform(0, 30, n)
    temp = rng.uniform(-5, 5, n)
    constant = np.full(n, 1.0)  # never varies within a group
    features = np.column_stack([temp, age, constant])
    y = 0.3 * temp - 0.1 * age + np.where(groups == 0, 85.0, 70.0)

    fit = fit_within_coffee(features, y, groups, min_within_range=0.5)
    assert fit.coefficients == pytest.approx([0.3, -0.1, 0.0], abs=1e-9)
    assert list(fit.active) == [True, True, False]
    assert fit.intercepts == pytest.approx([85.0, 70.0], abs=1e-9)
    assert fit.r_squared == 1.0


# ── Storage ──────────────────────────────────────────────────────────────────


def test_media_storage_save_and_delete(tmp_path: Path) -> None:
    """Uploads get UUID names with an allowed extension and can be deleted."""
    storage = MediaStorage(tmp_path / "media")
    upload = FileStorage(BytesIO(b"data"), filename="label.EXE")
    name = storage.save_upload(upload, {".jpg"}, ".jpg")
    assert name.endswith(".jpg")
    assert (tmp_path / "media" / name).read_bytes() == b"data"
    storage.delete(name)
    storage.delete(name)  # deleting a missing file is a no-op
    assert not (tmp_path / "media" / name).exists()


def test_media_storage_telemetry_pair(tmp_path: Path) -> None:
    """Telemetry JSON and its thumbnail are saved and deleted together."""
    storage = MediaStorage(tmp_path)
    name = storage.save_telemetry(b"{}", b"png")
    assert (storage.telemetry_dir / name).exists()
    assert (storage.telemetry_dir / thumbnail_name(name)).exists()
    storage.delete_telemetry(name)
    assert list(storage.telemetry_dir.iterdir()) == []


def test_media_storage_telemetry_cleans_up_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed write leaves no partial files behind."""
    storage = MediaStorage(tmp_path)
    original = Path.replace
    calls = {"n": 0}

    def failing_replace(self: Path, target: Path) -> Path:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)
    with pytest.raises(OSError):
        storage.save_telemetry(b"{}", b"png")
    assert list(storage.telemetry_dir.iterdir()) == []
