"""Grind setting format validation."""

import re

from coffee_records.config import GrindersConfig
from coffee_records.services.grind_notation import GrinderFamily, classify_grinder

_DUAL_SCALE_RE = re.compile(r"^\d+\+\d+( \d+/\d+)?$")
_SINGLE_NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")

_RULES: dict[GrinderFamily, tuple[re.Pattern[str], str]] = {
    GrinderFamily.DUAL_SCALE: (
        _DUAL_SCALE_RE,
        'Expected format: "#+# #/#" (e.g. "8+5 1/2")',
    ),
    GrinderFamily.SINGLE_NUMBER: (
        _SINGLE_NUMBER_RE,
        "Expected a single number (e.g. 19.5)",
    ),
}


def validate_grind_setting(
    grind_setting: str,
    grinder_make: str,
    grinder_model: str,
    grinders: GrindersConfig | None = None,
) -> str | None:
    """Return an error message if grind_setting is invalid for the given grinder, else None.

    Args:
        grind_setting: The grind setting string to validate.
        grinder_make: The grinder manufacturer.
        grinder_model: The grinder model name.
        grinders: Grinder keyword settings (defaults to built-in settings).

    Returns:
        An error string if invalid, or None if valid (or grinder type is unrecognised).
    """
    family = classify_grinder(grinder_make, grinder_model, grinders)
    if family is None:
        return None
    pattern, message = _RULES[family]
    return None if pattern.match(grind_setting) else message
