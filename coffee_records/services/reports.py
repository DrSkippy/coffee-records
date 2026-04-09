"""Report query logic for trends and statistics."""

import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from coffee_records.models.coffee import Coffee
from coffee_records.models.equipment import BrewingDevice, Grinder
from coffee_records.models.grind_model import GrindModelCoffeeIntercept, GrindModelTraining
from coffee_records.models.shot import DrinkType, Shot

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


def target_shot_time_wma(
    session: Session,
    coffee_id: int,
    grinder_id: int | None = None,
    device_id: int | None = None,
) -> tuple[float | None, int]:
    """Weighted moving average of (extraction_time + extraction_delta) for espresso shots.

    Shots are ordered oldest-first (i=0) to most recent (i=N-1), giving higher
    weight to recent shots.  Formula: wma = Σ(i+1)(tᵢ+dtᵢ) / Σ(i+1) where
    the denominator equals N*(N+1)/2.

    Args:
        session: SQLAlchemy session.
        coffee_id: Filter to shots for this coffee bag.
        grinder_id: Optional filter by grinder.
        device_id: Optional filter by brewing device.

    Returns:
        Tuple of (wma rounded to 1 decimal place, shot count used).
        wma is None when no qualifying shots exist.
    """
    query = session.query(Shot.extraction_time, Shot.extraction_delta).filter(
        Shot.coffee_id == coffee_id,
        Shot.extraction_time.isnot(None),
        Shot.drink_type.in_(
            [DrinkType.americano, DrinkType.latte, DrinkType.cappuccino]
        ),
    )
    if grinder_id is not None:
        query = query.filter(Shot.grinder_id == grinder_id)
    if device_id is not None:
        query = query.filter(Shot.device_id == device_id)

    rows = query.order_by(Shot.date.asc(), Shot.created_at.asc()).all()

    if not rows:
        return None, 0

    weighted_sum = sum(
        (i + 1) * (row.extraction_time + (row.extraction_delta or 0.0))
        for i, row in enumerate(rows)
    )
    n = len(rows)
    denominator = n * (n + 1) / 2
    return round(weighted_sum / denominator, 1), n


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

    # Target shot time: weighted moving average of (extraction_time + extraction_delta)
    # across all espresso-based shots for this coffee (recent shots weighted higher).
    target_shot_time, _ = target_shot_time_wma(session, coffee_id)

    return {
        "coffee_id": coffee_id,
        "roast_date": roast_date.isoformat(),
        "grinders": result_grinders,
        "target_shot_time": target_shot_time,
    }


# ---------------------------------------------------------------------------
# Multivariate grind model — alternating OLS fitting
# ---------------------------------------------------------------------------

_ESPRESSO_TYPES = [DrinkType.americano, DrinkType.latte, DrinkType.cappuccino]
_DEFAULT_INTERCEPT: float = float(parse_grind_numeric("8+5") or 85.0)


def _load_training_shots(session: Session, grinder_id: int) -> list[Shot]:
    """Load all shots eligible for grind model training for a grinder.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder primary key.

    Returns:
        List of Shot instances ordered by date asc, created_at asc.
    """
    return (
        session.query(Shot)
        .options(joinedload(Shot.coffee))
        .join(Coffee, Shot.coffee_id == Coffee.id)
        .filter(
            Shot.grinder_id == grinder_id,
            Shot.drink_type.in_(_ESPRESSO_TYPES),
            Shot.grind_setting.isnot(None),
            Shot.grinder_temp_before.isnot(None),
            Shot.coffee_id.isnot(None),
            Shot.dose_weight.isnot(None),
            Shot.final_weight.isnot(None),
            Shot.extraction_time.isnot(None),
            Coffee.roast_date.isnot(None),
        )
        .order_by(Shot.date.asc(), Shot.created_at.asc())
        .all()
    )


def _first_date_per_coffee(shots: list[Shot]) -> dict[int, date]:
    """Return the earliest shot date for each coffee_id in the list.

    Args:
        shots: List of Shot instances.

    Returns:
        Mapping of coffee_id to earliest date.
    """
    result: dict[int, date] = {}
    for shot in shots:
        cid = shot.coffee_id
        if cid is not None and (cid not in result or shot.date < result[cid]):
            result[cid] = shot.date
    return result


def fit_grind_model(
    session: Session,
    grinder_id: int,
) -> dict[str, Any]:
    """Fit the multivariate grind model for a grinder using alternating OLS.

    Model (a1 = 1, grind_setting is the OLS dependent variable):
        grind_setting = a0*(temp-65) + a2*(extraction_time - target_time)
                      + a3*(dose-20) + a4*age_days + a5*(yield - 2*dose) + c(coffee_id)

    Fitting uses an alternating least-squares procedure:
      - Stage 1: Fix per-coffee intercepts c, fit global coefficients a0-a5 via lstsq.
      - Stage 2: Fix a0-a5, update each c as the mean residual for that coffee.
      - Repeat until convergence (tol=1e-8) or 200 iterations.

    Warm-starts from the most recent existing training for this grinder.
    New coffees (not in prior training) are initialized to parse_grind_numeric("8+5") = 85.0.

    Persists the result to grind_model_trainings + grind_model_coffee_intercepts.

    Args:
        session: SQLAlchemy session.
        grinder_id: Grinder to fit for.

    Returns:
        Dict matching GrindModelTrainingResponse schema.

    Raises:
        ValueError: "grinder_not_found" | "insufficient_data"
    """
    grinder = session.get(Grinder, grinder_id)
    if grinder is None:
        raise ValueError("grinder_not_found")
    grinder_label = f"{grinder.make} {grinder.model}"

    all_shots = _load_training_shots(session, grinder_id)
    n_available = len(all_shots)

    first_dates = _first_date_per_coffee(all_shots)

    # Compute target_shot_time per coffee (for the extraction_time feature)
    unique_coffee_ids_all = list({s.coffee_id for s in all_shots if s.coffee_id is not None})
    target_time_per_coffee: dict[int, float | None] = {
        cid: target_shot_time_wma(session, cid, grinder_id=grinder_id)[0]
        for cid in unique_coffee_ids_all
    }

    # Build usable rows (after filtering first-day shots and unparseable grind settings)
    rows: list[dict[str, Any]] = []
    for shot in all_shots:
        cid = shot.coffee_id
        if cid is None:
            continue
        if shot.date == first_dates.get(cid):
            continue
        y = parse_grind_numeric(shot.grind_setting)  # type: ignore[arg-type]
        if y is None:
            continue
        target_time = target_time_per_coffee.get(cid)
        if target_time is None:
            continue
        coffee = shot.coffee
        if coffee is None or coffee.roast_date is None:
            continue
        age_days = (shot.date - coffee.roast_date).days
        rows.append(
            {
                "shot": shot,
                "y": y,
                "coffee_id": cid,
                "x0": float(shot.grinder_temp_before) - 65.0,  # type: ignore[arg-type]
                "x2": float(shot.extraction_time) - target_time,  # type: ignore[arg-type]
                "x3": float(shot.dose_weight) - 20.0,  # type: ignore[arg-type]
                "x4": float(age_days),
                "x5": float(shot.final_weight) - 2.0 * float(shot.dose_weight),  # type: ignore[arg-type]
            }
        )

    n_used = len(rows)
    if n_used < 3:
        raise ValueError("insufficient_data")

    unique_coffees = sorted({r["coffee_id"] for r in rows})
    n_coffees = len(unique_coffees)
    coffee_to_idx = {cid: i for i, cid in enumerate(unique_coffees)}

    y_arr = np.array([r["y"] for r in rows], dtype=float)
    X_global = np.column_stack(
        [
            [r["x0"] for r in rows],
            [r["x2"] for r in rows],
            [r["x3"] for r in rows],
            [r["x4"] for r in rows],
            [r["x5"] for r in rows],
        ]
    )
    coffee_indices = [coffee_to_idx[r["coffee_id"]] for r in rows]

    # Warm-start intercepts from last training; fall back to default
    last_training = (
        session.query(GrindModelTraining)
        .filter(GrindModelTraining.grinder_id == grinder_id)
        .order_by(GrindModelTraining.trained_at.desc())
        .first()
    )
    c = np.full(n_coffees, _DEFAULT_INTERCEPT)
    if last_training is not None:
        prior = {ci.coffee_id: ci.intercept for ci in last_training.coffee_intercepts}
        for i, cid in enumerate(unique_coffees):
            if cid in prior:
                c[i] = prior[cid]

    # Alternating OLS
    MAX_ITER = 200
    TOL = 1e-8
    a = np.zeros(5)
    converged = False
    n_iterations = 0

    for iteration in range(MAX_ITER):
        a_prev = a.copy()
        c_prev = c.copy()

        # Stage 1: fit global coefficients
        c_per_shot = np.array([c[idx] for idx in coffee_indices])
        y_adj = y_arr - c_per_shot
        a, _, _, _ = np.linalg.lstsq(X_global, y_adj, rcond=None)

        # Stage 2: fit per-coffee intercepts
        residuals = y_arr - X_global @ a
        for i in range(n_coffees):
            mask = np.array([idx == i for idx in coffee_indices])
            if mask.sum() > 0:
                c[i] = float(residuals[mask].mean())

        n_iterations = iteration + 1
        if (
            iteration > 0
            and float(np.max(np.abs(a - a_prev))) < TOL
            and float(np.max(np.abs(c - c_prev))) < TOL
        ):
            converged = True
            break

    # R²
    c_per_shot_final = np.array([c[idx] for idx in coffee_indices])
    y_pred_arr = X_global @ a + c_per_shot_final
    ss_res = float(np.sum((y_arr - y_pred_arr) ** 2))
    ss_tot = float(np.sum((y_arr - float(y_arr.mean())) ** 2))
    r_squared: float | None = round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else None

    # Persist
    now = datetime.now(tz=timezone.utc)
    training = GrindModelTraining(
        grinder_id=grinder_id,
        trained_at=now,
        n_shots_available=n_available,
        n_shots_used=n_used,
        n_coffees=n_coffees,
        n_iterations=n_iterations,
        converged=converged,
        r_squared=r_squared,
        a0=round(float(a[0]), 8),
        a2=round(float(a[1]), 8),
        a3=round(float(a[2]), 8),
        a4=round(float(a[3]), 8),
        a5=round(float(a[4]), 8),
    )
    session.add(training)
    session.flush()

    coffee_names = {
        obj.id: obj.name
        for obj in session.query(Coffee).filter(Coffee.id.in_(unique_coffees)).all()
    }
    for i, cid in enumerate(unique_coffees):
        session.add(
            GrindModelCoffeeIntercept(
                training_id=training.id,
                coffee_id=cid,
                intercept=round(float(c[i]), 8),
            )
        )
    session.commit()

    return {
        "training_id": training.id,
        "grinder_id": grinder_id,
        "grinder_label": grinder_label,
        "trained_at": now,
        "n_shots_available": n_available,
        "n_shots_used": n_used,
        "n_coffees": n_coffees,
        "n_iterations": n_iterations,
        "converged": converged,
        "r_squared": r_squared,
        "a0": round(float(a[0]), 8),
        "a2": round(float(a[1]), 8),
        "a3": round(float(a[2]), 8),
        "a4": round(float(a[3]), 8),
        "a5": round(float(a[4]), 8),
        "coffee_intercepts": [
            {
                "coffee_id": cid,
                "coffee_name": coffee_names.get(cid),
                "intercept": round(float(c[i]), 8),
            }
            for i, cid in enumerate(unique_coffees)
        ],
    }


def get_grind_model_params(
    session: Session,
    grinder_id: int,
    training_id: int | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Load grind model parameters and projected data points for plotting.

    Args:
        session: SQLAlchemy session.
        grinder_id: Required — restricts to trainings for this grinder.
        training_id: If given, load this specific training run.
        as_of: If given, load the most recent training whose trained_at date
               is on or before this date.  Ignored if training_id is given.
               Defaults to the most recent training.

    Returns:
        Dict matching GrindModelParamsResponse schema (includes data points
        and per-coffee target shot times for the shot planner).

    Raises:
        ValueError: "grinder_not_found" | "no_training"
    """
    grinder = session.get(Grinder, grinder_id)
    if grinder is None:
        raise ValueError("grinder_not_found")
    grinder_label = f"{grinder.make} {grinder.model}"

    q = (
        session.query(GrindModelTraining)
        .options(joinedload(GrindModelTraining.coffee_intercepts))
        .filter(GrindModelTraining.grinder_id == grinder_id)
    )
    if training_id is not None:
        q = q.filter(GrindModelTraining.id == training_id)
    elif as_of is not None:
        cutoff = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=timezone.utc)
        q = q.filter(GrindModelTraining.trained_at <= cutoff)

    training = q.order_by(GrindModelTraining.trained_at.desc()).first()
    if training is None:
        raise ValueError("no_training")

    intercept_map: dict[int, float] = {
        ci.coffee_id: ci.intercept for ci in training.coffee_intercepts
    }
    coffee_ids_in_model = sorted(intercept_map.keys())

    coffee_names = {
        obj.id: obj.name
        for obj in session.query(Coffee).filter(Coffee.id.in_(coffee_ids_in_model)).all()
    }

    # Per-coffee target shot times
    target_times = []
    target_time_map: dict[int, float | None] = {}
    for cid in coffee_ids_in_model:
        wma, _ = target_shot_time_wma(session, cid, grinder_id=grinder_id)
        target_time_map[cid] = wma
        target_times.append({"coffee_id": cid, "target_shot_time": wma})

    # Re-query shots for plotting (all current qualifying shots for coffees in model)
    shots = (
        session.query(Shot)
        .options(joinedload(Shot.coffee))
        .join(Coffee, Shot.coffee_id == Coffee.id)
        .filter(
            Shot.grinder_id == grinder_id,
            Shot.drink_type.in_(_ESPRESSO_TYPES),
            Shot.grind_setting.isnot(None),
            Shot.grinder_temp_before.isnot(None),
            Shot.coffee_id.in_(coffee_ids_in_model),
            Shot.dose_weight.isnot(None),
            Shot.final_weight.isnot(None),
            Shot.extraction_time.isnot(None),
            Coffee.roast_date.isnot(None),
        )
        .order_by(Shot.date.asc(), Shot.created_at.asc())
        .all()
    )

    first_dates = _first_date_per_coffee(shots)
    a_vec = [training.a0, training.a2, training.a3, training.a4, training.a5]

    points: list[dict[str, Any]] = []
    for shot in shots:
        cid = shot.coffee_id
        if cid is None:
            continue
        if shot.date == first_dates.get(cid):
            continue
        y = parse_grind_numeric(shot.grind_setting)  # type: ignore[arg-type]
        if y is None:
            continue
        target_time = target_time_map.get(cid)
        if target_time is None:
            continue
        c_val = intercept_map.get(cid)
        if c_val is None:
            continue
        coffee = shot.coffee
        if coffee is None or coffee.roast_date is None:
            continue
        age_days = (shot.date - coffee.roast_date).days
        x = [
            float(shot.grinder_temp_before) - 65.0,  # type: ignore[arg-type]
            float(shot.extraction_time) - target_time,  # type: ignore[arg-type]
            float(shot.dose_weight) - 20.0,  # type: ignore[arg-type]
            float(age_days),
            float(shot.final_weight) - 2.0 * float(shot.dose_weight),  # type: ignore[arg-type]
        ]
        y_pred = sum(av * xi for av, xi in zip(a_vec, x)) + c_val
        points.append(
            {
                "shot_id": shot.id,
                "date": shot.date.isoformat(),
                "age_days": age_days,
                "temp_offset": round(float(shot.grinder_temp_before) - 65.0, 2),  # type: ignore[arg-type]
                "grind": round(y, 4),
                "grind_str": format_grind_numeric(y),
                "grind_predicted": round(y_pred, 4),
                "grind_predicted_str": format_grind_numeric(y_pred),
            }
        )

    return {
        "training_id": training.id,
        "grinder_id": grinder_id,
        "grinder_label": grinder_label,
        "trained_at": training.trained_at,
        "n_shots_available": training.n_shots_available,
        "n_shots_used": training.n_shots_used,
        "n_coffees": training.n_coffees,
        "n_iterations": training.n_iterations,
        "converged": training.converged,
        "r_squared": training.r_squared,
        "a0": training.a0,
        "a2": training.a2,
        "a3": training.a3,
        "a4": training.a4,
        "a5": training.a5,
        "coffee_intercepts": [
            {
                "coffee_id": cid,
                "coffee_name": coffee_names.get(cid),
                "intercept": intercept_map[cid],
            }
            for cid in coffee_ids_in_model
        ],
        "points": points,
        "target_times": target_times,
    }
