"""Beanconqueror ``S.T`` brew-time notation (seconds, then a tenths digit).

The part after the dot is a count of tenths, not a decimal fraction, so
``"0.10"`` means 1.0 s. ``float()`` gives the wrong answer for any value with
two or more digits after the dot.
"""

import math

TENTHS_PER_SECOND = 10


def parse_brew_time(value: object) -> float:
    """Parse a brew time in ``S.T`` notation (or a plain number) to seconds.

    Args:
        value: Raw brew_time value (string or number).

    Returns:
        Elapsed seconds.

    Raises:
        ValueError: If the value is malformed or not finite.
    """
    text = str(value)
    if "." in text:
        seconds, tenths = text.split(".", 1)
        result = int(seconds) + int(tenths) / TENTHS_PER_SECOND
    else:
        result = float(text)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite brew_time: {text}")
    return result


def format_brew_time(elapsed: float) -> str:
    """Format seconds as Beanconqueror ``S.T`` brew time (T = tenths).

    Args:
        elapsed: Seconds since the start of the shot.

    Returns:
        E.g. ``37.908`` -> ``"37.9"``, ``0.96`` -> ``"1.0"``.
    """
    tenths = round(elapsed * TENTHS_PER_SECOND)
    return f"{tenths // TENTHS_PER_SECOND}.{tenths % TENTHS_PER_SECOND}"
