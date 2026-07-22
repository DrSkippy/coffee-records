"""Grind setting format validation."""

import re

_MAZZER_RE = re.compile(r"^\d+\+\d+( \d+/\d+)?$")
_SINGLE_FLOAT_RE = re.compile(r"^\d+(\.\d+)?$")

_SINGLE_FLOAT_GRINDERS = ("option-o", "timemore", "baratza")


def validate_grind_setting(
    grind_setting: str, grinder_make: str, grinder_model: str
) -> str | None:
    """Return an error message if grind_setting is invalid for the given grinder, else None.

    Args:
        grind_setting: The grind setting string to validate.
        grinder_make: The grinder manufacturer.
        grinder_model: The grinder model name.

    Returns:
        An error string if invalid, or None if valid (or grinder type is unrecognised).
    """
    name = f"{grinder_make} {grinder_model}".lower()
    if "mazzer" in name:
        if not _MAZZER_RE.match(grind_setting):
            return 'Expected format: "#+# #/#" (e.g. "8+5 1/2")'
    elif any(g in name for g in _SINGLE_FLOAT_GRINDERS):
        if not _SINGLE_FLOAT_RE.match(grind_setting):
            return "Expected a single number (e.g. 19.5)"
    return None
