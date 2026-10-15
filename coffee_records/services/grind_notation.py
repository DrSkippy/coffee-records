"""Grind-setting notation: grinder families, parsing and formatting.

Two notations are in use:

* **Dual scale** (e.g. Mazzer): ``"g+h [n/d]"`` where ``g`` is the coarse ring
  and ``h`` the fine ring, encoded numerically as ``10*g + h + n/d``
  (``"8+7 1/2"`` → 87.5).
* **Single number** (e.g. Baratza, Option-O, Timemore): a plain decimal.
"""

import enum
import logging
import re

from coffee_records.config import GrindersConfig

logger = logging.getLogger(__name__)

# Each coarse-ring step is worth this many fine-ring steps.
DUAL_SCALE_BASE = 10
# Formatted fractions are rounded to the nearest 1/FRACTION_DENOMINATOR.
FRACTION_DENOMINATOR = 4

_UNICODE_FRACTIONS: dict[str, str] = {
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
}
_QUARTER_LABELS: dict[float, str] = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}
_TRAILING_FRACTION_RE = re.compile(r"(\d/\d+)$")


class GrinderFamily(enum.Enum):
    """Grind-setting notation family of a grinder."""

    DUAL_SCALE = "dual_scale"
    SINGLE_NUMBER = "single_number"


def classify_grinder(
    make: str, model: str, grinders: GrindersConfig | None = None
) -> GrinderFamily | None:
    """Classify a grinder's notation from its make and model text.

    Args:
        make: Grinder manufacturer.
        model: Grinder model name.
        grinders: Keyword configuration (defaults to built-in settings).

    Returns:
        The grinder family, or None if unrecognised.
    """
    grinders = grinders or GrindersConfig()
    label = f"{make} {model}".lower()
    if any(keyword in label for keyword in grinders.dual_scale_keywords):
        return GrinderFamily.DUAL_SCALE
    if any(keyword in label for keyword in grinders.single_number_keywords):
        return GrinderFamily.SINGLE_NUMBER
    return None


def _parse_fraction(text: str) -> float | None:
    """Parse ``"n/d"`` to a float.

    Args:
        text: Fraction text.

    Returns:
        The value, or None if malformed or the denominator is zero.
    """
    try:
        numerator, denominator = text.split("/")
        return int(numerator) / int(denominator)
    except (ValueError, ZeroDivisionError):
        logger.warning("Unparseable grind fraction %r", text)
        return None


def _parse_dual_scale(raw: str) -> float | None:
    """Parse dual-scale notation such as ``"8+7 1/2"`` or ``"8+71/2"``.

    Args:
        raw: Grind setting containing ``+``, Unicode fractions already expanded.

    Returns:
        ``10*g + h + fraction``, or None if any part is malformed.
    """
    parts = [part.strip() for part in raw.split("+", 2)]
    try:
        coarse = int(parts[0])
    except ValueError:
        return None

    # parts[1] may have an embedded fraction at the end: "71/2" → h=7, frac="1/2"
    # Search for a fraction pattern (\d+/\d+) at the end of the token.
    fine_text = parts[1]
    fraction_text = parts[2] if len(parts) == 3 else ""
    if not fraction_text:
        match = _TRAILING_FRACTION_RE.search(fine_text)
        if match:
            fraction_text = match.group(1)
            fine_text = fine_text[: match.start()].strip()

    try:
        fine = int(fine_text) if fine_text else 0
    except ValueError:
        return None

    fraction = 0.0
    if fraction_text:
        parsed = _parse_fraction(fraction_text)
        if parsed is None:
            return None
        fraction = parsed

    return float(coarse * DUAL_SCALE_BASE + fine) + fraction


def parse_grind_numeric(s: str) -> float | None:
    """Convert a grind setting string to a single float.

    Handles Mazzer dual-scale notation (e.g. "8+7 1/2" → 87.5) and plain
    decimal values (e.g. "19.5" → 19.5).

    Args:
        s: Raw grind setting string from the database.

    Returns:
        Numeric value, or None if the string (including any fraction) cannot
        be parsed.
    """
    raw = s.strip()
    for unicode_fraction, ascii_fraction in _UNICODE_FRACTIONS.items():
        raw = raw.replace(unicode_fraction, ascii_fraction)
    if "+" in raw:
        return _parse_dual_scale(raw)
    try:
        return float(raw)
    except ValueError:
        return None


def format_grind_numeric(v: float, grinders: GrindersConfig | None = None) -> str:
    """Convert a numeric grind value back to a human-readable string.

    Values at or above ``dual_scale_min_value`` are formatted as Mazzer
    dual-scale notation "g+h [frac]" with the fractional part rounded to the
    nearest ¼. Smaller values are returned as plain decimals.

    Args:
        v: Numeric grind value (e.g. 87.5).
        grinders: Notation settings (defaults to built-in settings).

    Returns:
        Formatted string (e.g. "8+7 1/2").
    """
    grinders = grinders or GrindersConfig()
    # Values below the threshold are assumed to be single-number grinder
    # settings (e.g. Baratza). Mazzer g+h values start at g=3 (→30) at
    # minimum; in practice g=7-9.
    if v < grinders.dual_scale_min_value:
        return str(round(v, 2)).rstrip("0").rstrip(".")

    coarse = int(v) // DUAL_SCALE_BASE
    remainder = v - coarse * DUAL_SCALE_BASE
    fine = int(remainder)
    fraction = round((remainder - fine) * FRACTION_DENOMINATOR) / FRACTION_DENOMINATOR

    if fraction >= 1.0:
        fine += 1
        fraction = 0.0
    if fraction == 0.0:
        return f"{coarse}+{fine}"
    return f"{coarse}+{fine} {_QUARTER_LABELS.get(fraction, str(fraction))}"
