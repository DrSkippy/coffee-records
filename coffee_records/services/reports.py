"""Report query logic for trends and statistics."""

import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from coffee_records.models.coffee import Coffee
from coffee_records.models.equipment import BrewingDevice, Grinder
from coffee_records.models.shot import Shot

logger = logging.getLogger(__name__)


def _default_range() -> tuple[date, date]:
    """Return the default 30-day date range (inclusive).

    Returns:
        Tuple of (date_from, date_to).
    """
    today = date.today()
    return today - timedelta(days=30), today


def dose_yield_over_time(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    coffee_id: int | None = None,
    grinder_id: int | None = None,
    device_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return dose weight vs final weight ratio per shot over time.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.
        coffee_id: Optional filter by coffee.
        grinder_id: Optional filter by grinder.
        device_id: Optional filter by brewing device.

    Returns:
        List of dicts with keys: date, shot_id, dose_weight, final_weight, ratio.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    q = (
        session.query(
            Shot.date,
            Shot.id,
            Shot.dose_weight,
            Shot.final_weight,
            Shot.device_id,
            BrewingDevice.make,
            BrewingDevice.model,
        )
        .outerjoin(BrewingDevice, Shot.device_id == BrewingDevice.id)
        .filter(Shot.date >= date_from, Shot.date <= date_to)
        .filter(Shot.dose_weight.isnot(None), Shot.final_weight.isnot(None))
    )
    if coffee_id is not None:
        q = q.filter(Shot.coffee_id == coffee_id)
    if grinder_id is not None:
        q = q.filter(Shot.grinder_id == grinder_id)
    if device_id is not None:
        q = q.filter(Shot.device_id == device_id)
    rows = q.order_by(Shot.date).all()
    results = []
    for row in rows:
        ratio = row.final_weight / row.dose_weight if row.dose_weight else None
        device_label = f"{row.make} {row.model}" if row.make else None
        results.append(
            {
                "date": row.date.isoformat(),
                "shot_id": row.id,
                "dose_weight": row.dose_weight,
                "final_weight": row.final_weight,
                "ratio": round(ratio, 3) if ratio is not None else None,
                "device_id": row.device_id,
                "device_label": device_label,
            }
        )
    return results


def shots_per_day(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    coffee_id: int | None = None,
    grinder_id: int | None = None,
    device_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return shot count grouped by date.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.
        coffee_id: Optional filter by coffee.
        grinder_id: Optional filter by grinder.
        device_id: Optional filter by brewing device.

    Returns:
        List of dicts with keys: date, count.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    q = (
        session.query(Shot.date, func.count(Shot.id).label("count"))
        .filter(Shot.date >= date_from, Shot.date <= date_to)
    )
    if coffee_id is not None:
        q = q.filter(Shot.coffee_id == coffee_id)
    if grinder_id is not None:
        q = q.filter(Shot.grinder_id == grinder_id)
    if device_id is not None:
        q = q.filter(Shot.device_id == device_id)
    rows = q.group_by(Shot.date).order_by(Shot.date).all()
    return [{"date": row.date.isoformat(), "count": row.count} for row in rows]


def extraction_trends(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    coffee_id: int | None = None,
    grinder_id: int | None = None,
    device_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return extraction time per shot over time.

    Args:
        session: SQLAlchemy session.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.
        coffee_id: Optional filter by coffee.
        grinder_id: Optional filter by grinder.
        device_id: Optional filter by brewing device.

    Returns:
        List of dicts with keys: date, shot_id, extraction_time.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    q = (
        session.query(
            Shot.date,
            Shot.id,
            Shot.extraction_time,
            Shot.device_id,
            BrewingDevice.make,
            BrewingDevice.model,
        )
        .outerjoin(BrewingDevice, Shot.device_id == BrewingDevice.id)
        .filter(Shot.date >= date_from, Shot.date <= date_to)
        .filter(Shot.extraction_time.isnot(None))
    )
    if coffee_id is not None:
        q = q.filter(Shot.coffee_id == coffee_id)
    if grinder_id is not None:
        q = q.filter(Shot.grinder_id == grinder_id)
    if device_id is not None:
        q = q.filter(Shot.device_id == device_id)
    rows = q.order_by(Shot.date).all()
    return [
        {
            "date": row.date.isoformat(),
            "shot_id": row.id,
            "extraction_time": row.extraction_time,
            "device_id": row.device_id,
            "device_label": f"{row.make} {row.model}" if row.make else None,
        }
        for row in rows
    ]


def by_coffee(
    session: Session,
    coffee_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Return stats for all shots using a specific coffee bag.

    Args:
        session: SQLAlchemy session.
        coffee_id: Coffee primary key.
        date_from: Start date (inclusive). Defaults to 30 days ago.
        date_to: End date (inclusive). Defaults to today.

    Returns:
        Dict with total_shots, avg_dose, avg_final_weight, avg_extraction_time, avg_ratio, shots list.
    """
    if date_from is None or date_to is None:
        d_from, d_to = _default_range()
        date_from = date_from or d_from
        date_to = date_to or d_to

    rows = (
        session.query(Shot)
        .filter(
            Shot.coffee_id == coffee_id,
            Shot.date >= date_from,
            Shot.date <= date_to,
        )
        .order_by(Shot.date)
        .all()
    )

    doses = [s.dose_weight for s in rows if s.dose_weight is not None]
    finals = [s.final_weight for s in rows if s.final_weight is not None]
    extractions = [s.extraction_time for s in rows if s.extraction_time is not None]
    ratios = [
        s.final_weight / s.dose_weight
        for s in rows
        if s.final_weight is not None and s.dose_weight is not None and s.dose_weight > 0
    ]

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "coffee_id": coffee_id,
        "total_shots": len(rows),
        "avg_dose": avg(doses),
        "avg_final_weight": avg(finals),
        "avg_extraction_time": avg(extractions),
        "avg_ratio": avg(ratios),
        "shots": [
            {
                "date": s.date.isoformat(),
                "shot_id": s.id,
                "dose_weight": s.dose_weight,
                "final_weight": s.final_weight,
                "extraction_time": s.extraction_time,
            }
            for s in rows
        ],
    }


# ---------------------------------------------------------------------------
# Grind setting helpers
# ---------------------------------------------------------------------------

_UNICODE_FRACS: dict[str, str] = {
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
}


def parse_grind_numeric(s: str) -> float | None:
    """Convert a grind setting string to a single float.

    Handles Mazzer dual-scale notation (e.g. "8+7 1/2" → 87.5) and plain
    decimal values (e.g. "19.5" → 19.5).

    Args:
        s: Raw grind setting string from the database.

    Returns:
        Numeric value, or None if the string cannot be parsed.
    """
    raw = s.strip()
    for uni, asc in _UNICODE_FRACS.items():
        raw = raw.replace(uni, asc)

    if "+" in raw:
        parts = [p.strip() for p in raw.split("+", 2)]
        try:
            g = int(parts[0])
        except ValueError:
            return None

        # parts[1] may have an embedded fraction at the end: "71/2" → h=7, frac="1/2"
        # Search for a fraction pattern (\d+/\d+) at the end of the token.
        h_raw = parts[1]
        frac_str = parts[2] if len(parts) == 3 else ""

        if not frac_str:
            frac_m = re.search(r"(\d/\d+)$", h_raw)
            if frac_m:
                frac_str = frac_m.group(1)
                h_raw = h_raw[: frac_m.start()].strip()

        try:
            h = int(h_raw) if h_raw else 0
        except ValueError:
            return None

        frac_val = 0.0
        if frac_str:
            try:
                num_s, den_s = frac_str.split("/")
                frac_val = int(num_s) / int(den_s)
            except (ValueError, ZeroDivisionError):
                pass

        return float(g * 10 + h) + frac_val

    # Plain decimal
    try:
        return float(raw)
    except ValueError:
        return None


def format_grind_numeric(v: float) -> str:
    """Convert a numeric grind value back to a human-readable string.

    Values ≥ 10 are formatted as Mazzer dual-scale notation "g+h [frac]"
    with the fractional part rounded to the nearest ¼.  Values < 10 are
    returned as plain decimals.

    Args:
        v: Numeric grind value (e.g. 87.5).

    Returns:
        Formatted string (e.g. "8+7 1/2").
    """
    _FRAC_MAP = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}

    # Values below 30 are assumed to be single-number grinder settings (e.g. Baratza).
    # Mazzer g+h values start at g=3 (→30) at minimum; in practice g=7-9.
    if v < 30:
        return str(round(v, 2)).rstrip("0").rstrip(".")

    g = int(v) // 10
    remainder = v - g * 10
    h = int(remainder)
    frac = remainder - h
    frac_rounded = round(frac * 4) / 4  # round to nearest 0.25

    if frac_rounded >= 1.0:
        h += 1
        frac_rounded = 0.0

    if frac_rounded == 0.0:
        return f"{g}+{h}"

    frac_str = _FRAC_MAP.get(frac_rounded, str(frac_rounded))
    return f"{g}+{h} {frac_str}"


def _solve_3x3(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve a 3×3 linear system Ax = b via Gaussian elimination with partial pivoting.

    Args:
        A: 3×3 coefficient matrix (will be mutated).
        b: Right-hand side vector of length 3 (will be mutated).

    Returns:
        Solution vector [x0, x1, x2].

    Raises:
        ValueError: If the matrix is singular.
    """
    n = 3
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Partial pivot
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]

        pivot = M[col][col]
        if abs(pivot) < 1e-12:
            raise ValueError("singular matrix")

        for row in range(col + 1, n):
            factor = M[row][col] / pivot
            for j in range(col, n + 1):
                M[row][j] -= factor * M[col][j]

    # Back-substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]

    return x


def grind_regression(
    session: Session,
    coffee_id: int,
    grinder_id: int | None = None,
) -> dict[str, Any]:
    """Fit a bivariate linear regression to grind settings for a coffee bag.

    Model: y = a*x1 + b*x2 + c
      y  = grind setting (numeric)
      x1 = days since roast
      x2 = grinder_temp_before - 65

    Only shots from the same grinder are regressed together.  If grinder_id
    is omitted, the Mazzer grinder is used as the default.

    Args:
        session: SQLAlchemy session.
        coffee_id: Coffee primary key.
        grinder_id: Optional grinder filter.  Defaults to Mazzer.

    Returns:
        Dict with coffee_id, roast_date, and per-grinder regression results.

    Raises:
        ValueError: "not_found" | "no_roast_date" | "insufficient_data"
    """
    coffee = session.get(Coffee, coffee_id)
    if coffee is None:
        raise ValueError("not_found")
    if coffee.roast_date is None:
        raise ValueError("no_roast_date")
    roast_date = coffee.roast_date

    # Resolve default grinder (Mazzer) if none specified
    resolved_grinder_id = grinder_id
    if resolved_grinder_id is None:
        mazzer = next(
            (
                g
                for g in session.query(Grinder).all()
                if "mazzer" in f"{g.make} {g.model}".lower()
            ),
            None,
        )
        if mazzer is not None:
            resolved_grinder_id = mazzer.id
            logger.debug("grind_regression: defaulting to Mazzer grinder id=%d", mazzer.id)

    # Fetch shots
    q = (
        session.query(Shot)
        .filter(
            Shot.coffee_id == coffee_id,
            Shot.grind_setting.isnot(None),
            Shot.grinder_temp_before.isnot(None),
            Shot.grinder_id.isnot(None),
        )
    )
    if resolved_grinder_id is not None:
        q = q.filter(Shot.grinder_id == resolved_grinder_id)
    shots = q.order_by(Shot.date).all()

    # Group by grinder_id; parse grind setting
    groups: dict[int, list[tuple[Shot, float]]] = defaultdict(list)
    for shot in shots:
        y = parse_grind_numeric(shot.grind_setting)  # type: ignore[arg-type]
        if y is not None:
            groups[shot.grinder_id].append((shot, y))  # type: ignore[index]

    # Keep only groups with ≥ 3 usable points
    usable = {gid: pts for gid, pts in groups.items() if len(pts) >= 3}
    if not usable:
        raise ValueError("insufficient_data")

    # Pre-load grinder labels
    grinder_rows = {g.id: g for g in session.query(Grinder).all()}

    result_grinders: list[dict[str, Any]] = []

    for gid, pts in usable.items():
        x1s = [(s.date - roast_date).days for s, _ in pts]
        x2s = [float(s.grinder_temp_before) - 65.0 for s, _ in pts]  # type: ignore[arg-type]
        ys = [y for _, y in pts]
        n = len(pts)

        # Build normal equations AtA * p = Atb
        AtA: list[list[float]] = [
            [sum(a * b for a, b in zip(x1s, x1s)), sum(a * b for a, b in zip(x1s, x2s)), sum(x1s)],
            [sum(a * b for a, b in zip(x1s, x2s)), sum(a * b for a, b in zip(x2s, x2s)), sum(x2s)],
            [sum(x1s), sum(x2s), float(n)],
        ]
        Atb: list[float] = [
            sum(a * b for a, b in zip(x1s, ys)),
            sum(a * b for a, b in zip(x2s, ys)),
            sum(ys),
        ]

        try:
            a_coef, b_coef, c_coef = _solve_3x3(AtA, Atb)
        except ValueError:
            logger.warning("grind_regression: singular matrix for grinder_id=%d — skipping", gid)
            continue

        y_mean = sum(ys) / n
        ss_tot = sum((y - y_mean) ** 2 for y in ys)
        y_preds = [a_coef * x1 + b_coef * x2 + c_coef for x1, x2 in zip(x1s, x2s)]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(ys, y_preds))
        r_squared: float | None = round(1 - ss_res / ss_tot, 4) if ss_tot != 0 else None

        grinder_obj = grinder_rows.get(gid)
        grinder_label = f"{grinder_obj.make} {grinder_obj.model}" if grinder_obj else str(gid)

        points: list[dict[str, Any]] = []
        for (shot, y), x1, x2, y_pred in zip(pts, x1s, x2s, y_preds):
            points.append(
                {
                    "shot_id": shot.id,
                    "date": shot.date.isoformat(),
                    "x1": x1,
                    "x2": round(x2, 2),
                    "y": round(y, 4),
                    "y_str": format_grind_numeric(y),
                    "y_predicted": round(y_pred, 4),
                    "y_predicted_str": format_grind_numeric(y_pred),
                }
            )

        result_grinders.append(
            {
                "grinder_id": gid,
                "grinder_label": grinder_label,
                "n_shots": n,
                "coefficients": {
                    "a": round(a_coef, 6),
                    "b": round(b_coef, 6),
                    "c": round(c_coef, 6),
                },
                "r_squared": r_squared,
                "points": points,
            }
        )

    if not result_grinders:
        raise ValueError("insufficient_data")

    return {
        "coffee_id": coffee_id,
        "roast_date": roast_date.isoformat(),
        "grinders": result_grinders,
    }
