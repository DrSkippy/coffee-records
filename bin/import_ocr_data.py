#!/usr/bin/env python
"""Import OCR-processed CSV data into the coffee-records database.

Parses two CSVs produced by an OCR app from handwritten shot log sheets:
  - coffee_roasters.csv  : coffee bag definitions
  - coffee_shots.csv     : individual shot records

The OCR encodes a circled choice by wrapping it in parentheses or replacing the
first character with "0". Position (1-based) is the primary signal; letters are
logged as secondary confirmation.

Usage:
    poetry run python bin/import_ocr_data.py --dry-run --verbose
    poetry run python bin/import_ocr_data.py
"""

import argparse
import csv
import logging
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import load_config
from coffee_records.database import get_session, init_db
from coffee_records.models.coffee import Coffee, RoastLevel
from coffee_records.models.equipment import BrewingDevice, Grinder
from coffee_records.models.shot import DrinkType, Shot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared: circled-option decoder
# ---------------------------------------------------------------------------

def parse_circled(
    field: str,
    options: list[str],
    context: str = "",
) -> tuple[int | None, str | None, list[str]]:
    """Decode a circled-choice OCR field.

    The OCR encodes the selected value as either:
      - A token wrapped in parentheses: "(sc)sa ot"
      - The first character replaced by "0": "0md" -> position 0 selected

    Position (1-based) is the primary signal. The raw token letters are logged
    as secondary confirmation. Any mismatch between expected and actual letters
    at the matched position is recorded as a warning.

    Args:
        field:   Raw OCR string, e.g. "(sc)sa ot" or "0md"
        options: Ordered canonical tokens, e.g. ["sc", "sa", "ot"]
        context: Description for log messages, e.g. "shots row 3 brewer"

    Returns:
        (0-based index or None, resolved option string or None, list of warnings)
    """
    warnings: list[str] = []

    if not field or not field.strip():
        warnings.append(f"{context}: empty field, expected one of {options}")
        return None, None, warnings

    raw = field.strip()

    # Strategy 1: find parenthesized token  e.g. "(sc)sa ot" or "sc(sa)ot"
    paren_match = re.search(r"\(([^)]+)\)", raw)
    if paren_match:
        token = paren_match.group(1).strip()
        before = raw[: paren_match.start()]
        # Count non-whitespace chunks before the match to determine position
        preceding = re.findall(r"\S+", before)
        pos = len(preceding)

        if pos >= len(options):
            warnings.append(
                f"{context}: parenthesized token '{token}' at position {pos + 1} "
                f"exceeds options {options} — ignoring"
            )
            return None, None, warnings

        expected = options[pos]
        if token.lower() != expected.lower():
            warnings.append(
                f"{context}: token '{token}' at position {pos + 1} "
                f"doesn't match expected '{expected}' — using positional mapping to '{expected}'"
            )

        logger.debug(
            "parse_circled [%s]: raw=%r  paren_token=%r  position=%d  -> %r",
            context, raw, token, pos + 1, expected,
        )
        return pos, expected, warnings

    # Strategy 2: token starting with "0" (OCR artifact for circled first letter).
    # Only "0" is treated as the selection marker — "1" is just the letter "l" OCR'd.
    # Split on whitespace/slash to get tokens
    tokens = re.split(r"[\s/]+", raw)
    for i, tok in enumerate(tokens):
        if tok and tok[0] == "0" and i < len(options):
            expected = options[i]
            logger.debug(
                "parse_circled [%s]: raw=%r  zero-prefix token=%r at position %d -> %r",
                context, raw, tok, i + 1, expected,
            )
            return i, expected, warnings

    warnings.append(
        f"{context}: no circled selection found in {raw!r} "
        f"(options: {options}) — value will be null"
    )
    return None, None, warnings


# ---------------------------------------------------------------------------
# Field-level parsers
# ---------------------------------------------------------------------------

def parse_date(raw: str, year: int = 2026) -> date | None:
    """Parse an M/D string into a date using the given year.

    Args:
        raw:  Date string like "3/1" or "2/16"
        year: Year to apply (default 2026)

    Returns:
        date object or None on failure
    """
    cleaned = re.sub(r"[^0-9/]", "", raw.strip())
    if not cleaned:
        return None
    try:
        parts = cleaned.split("/")
        return date(year, int(parts[0]), int(parts[1]))
    except (ValueError, IndexError) as exc:
        logger.warning("parse_date: cannot parse %r — %s", raw, exc)
        return None


def parse_float(raw: str, context: str = "") -> float | None:
    """Parse a float, stripping ~ and whitespace.

    Args:
        raw:     Raw string, possibly "~67.5" or "  39 "
        context: Description for debug messages

    Returns:
        float or None on failure / empty
    """
    if not raw:
        return None
    cleaned = raw.strip().lstrip("~").strip()
    if not cleaned:
        return None
    # Strip trailing non-numeric garbage (e.g. "40.k" -> "40.", OCR artifact)
    cleaned = re.sub(r"[^\d.]+$", "", cleaned)
    if not cleaned or cleaned == ".":
        return None
    try:
        val = float(cleaned)
        if context:
            logger.debug("parse_float [%s]: %r -> %g", context, raw, val)
        return val
    except ValueError:
        logger.debug("parse_float [%s]: cannot parse %r", context, raw)
        return None


def parse_drink_weight(raw: str, context: str = "") -> str | None:
    """Parse the Drink Weight column into a note string.

    Rules:
      - "x" or "X" (stripped, case-insensitive) -> "shot rejected"
      - First extracted integer in range [40, 500] -> "drink weight: {n}g"
      - Otherwise -> None (discard)

    Args:
        raw:     Raw drink weight string
        context: Description for log messages

    Returns:
        Note string or None
    """
    cleaned = raw.strip()
    if not cleaned:
        return None

    if cleaned.lower() == "x":
        logger.debug("parse_drink_weight [%s]: %r -> shot rejected", context, raw)
        return "shot rejected"

    nums = re.findall(r"\d+", cleaned)
    if nums:
        n = int(nums[0])
        if 40 <= n <= 500:
            logger.debug("parse_drink_weight [%s]: %r -> drink weight %dg", context, raw, n)
            return f"drink weight: {n}g"
        logger.debug(
            "parse_drink_weight [%s]: %r -> %d out of range [40, 500], discarding",
            context, raw, n,
        )
    else:
        logger.debug("parse_drink_weight [%s]: %r -> no numeric content, discarding", context, raw)

    return None


def normalize_grind(raw: str) -> str:
    """Normalize a grind setting string.

    Replaces Unicode fraction ½ with "1/2" and strips surrounding whitespace.

    Args:
        raw: Raw grind setting

    Returns:
        Normalized string
    """
    return raw.strip().replace("\u00bd", "1/2")


def infer_grinder_key(grind_setting: str) -> str | None:
    """Infer which grinder was used from the grind setting format.

    Rules:
      - Contains "+" (e.g. "8+7", "8+7 1/2") -> "mazzer"
      - Plain integer or decimal (e.g. "19.5")  -> "baratza"
      - Anything else                            -> None

    Args:
        grind_setting: Normalized grind setting string

    Returns:
        "mazzer", "baratza", or None
    """
    if not grind_setting:
        return None
    if "+" in grind_setting:
        logger.debug("infer_grinder: %r contains '+' -> mazzer", grind_setting)
        return "mazzer"
    if re.match(r"^\d+(\.\d+)?$", grind_setting):
        logger.debug("infer_grinder: %r is numeric -> baratza", grind_setting)
        return "baratza"
    logger.debug("infer_grinder: %r -> unrecognized pattern, no grinder inferred", grind_setting)
    return None


# ---------------------------------------------------------------------------
# Column option maps
# ---------------------------------------------------------------------------

ROAST_OPTIONS = ["l", "m", "d"]
ROAST_MAP: dict[str, RoastLevel] = {
    "l": RoastLevel.light,
    "m": RoastLevel.medium,
    "d": RoastLevel.dark,
}

BREWER_OPTIONS = ["sc", "sa", "ot"]
BREWER_MAP: dict[str, str] = {
    "sc": "Scott",
    "sa": "Sara",
    "ot": "Other",
}

DRINK_OPTIONS = ["a", "cp", "l", "co"]
DRINK_MAP: dict[str, DrinkType] = {
    "a": DrinkType.americano,
    "cp": DrinkType.cappuccino,
    "l": DrinkType.latte,
    "co": DrinkType.drip,
}

BREW_METHOD_OPTIONS = ["e", "p", "d", "f"]
BREW_METHOD_LABELS: dict[str, str] = {
    "e": "espresso",
    "p": "pour_over",
    "d": "drip",
    "f": "immersion",
}


# ---------------------------------------------------------------------------
# CSV parsers
# ---------------------------------------------------------------------------

def parse_coffees(path: Path, year: int = 2026) -> list[dict[str, Any]]:
    """Parse the coffee_roasters.csv file into a list of coffee dicts.

    Each dict contains Coffee model fields plus a "code" key for linking to shots.

    Args:
        path: Path to the CSV file
        year: Year to apply to roast dates

    Returns:
        List of coffee dicts
    """
    coffees: list[dict[str, Any]] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            code = row.get("Code", "").strip()
            if not code:
                continue

            roaster = row.get("Coffee Roaster", "").strip()
            name = row.get("Coffee Name", "").strip()

            if not roaster and not name:
                logger.info("coffees row %d (code=%s): all fields empty — skipping", row_num, code)
                continue

            row_warnings: list[str] = []

            # Roast level
            roast_raw = row.get("Roast", "").strip()
            roast_idx, roast_key, w = parse_circled(
                roast_raw, ROAST_OPTIONS, context=f"coffees row {row_num} roast"
            )
            row_warnings.extend(w)
            roast_level = ROAST_MAP.get(roast_key) if roast_key else None

            # Roast date
            roast_date = parse_date(row.get("Roast Date", "").strip(), year)

            coffee: dict[str, Any] = {
                "code": code,
                "name": name,
                "roaster": roaster,
                "origin_country": row.get("Coffee Origin", "").strip() or None,
                "variety": row.get("Variety", "").strip() or None,
                "process": row.get("Process", "").strip() or None,
                "roast_level": roast_level,
                "roast_date": roast_date,
            }

            logger.info(
                "coffees row %d: code=%s  %s / %s  roast=%s  date=%s",
                row_num, code, roaster, name, roast_level, roast_date,
            )
            for warning in row_warnings:
                logger.warning("  %s", warning)

            coffees.append(coffee)

    return coffees


def parse_shots(path: Path, year: int = 2026) -> list[dict[str, Any]]:
    """Parse the coffee_shots.csv file into a list of shot dicts.

    Each dict contains Shot model fields plus "code" (for coffee lookup) and
    "_row" / "_grinder_key" (internal use, stripped before DB insert).

    Args:
        path: Path to the CSV file
        year: Year to apply to brew dates

    Returns:
        List of shot dicts
    """
    shots: list[dict[str, Any]] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            code = row.get("Code", "").strip()
            if not code:
                continue

            row_warnings: list[str] = []

            # Date (required)
            date_val = parse_date(row.get("Brew Date", "").strip(), year)
            if date_val is None:
                logger.warning("shots row %d: missing/invalid Brew Date — skipping row", row_num)
                continue

            # Brew method (logged only, not stored in DB)
            bm_idx, bm_key, w = parse_circled(
                row.get("Brew Method", "").strip(),
                BREW_METHOD_OPTIONS,
                context=f"shots row {row_num} brew_method",
            )
            row_warnings.extend(w)
            logger.debug(
                "shots row %d: brew_method=%s",
                row_num, BREW_METHOD_LABELS.get(bm_key or "", "unknown"),
            )

            # Brewer -> maker
            brewer_raw = row.get("Brewer", "").strip()
            _, brewer_key, w = parse_circled(
                brewer_raw, BREWER_OPTIONS, context=f"shots row {row_num} brewer"
            )
            row_warnings.extend(w)
            maker: str
            if brewer_key is not None:
                maker = BREWER_MAP[brewer_key]
            else:
                maker = "Unknown"
                row_warnings.append(
                    f"shots row {row_num}: could not decode brewer from {brewer_raw!r} — using 'Unknown'"
                )

            # Drink type
            drink_raw = row.get("Drink", "").strip()
            _, drink_key, w = parse_circled(
                drink_raw, DRINK_OPTIONS, context=f"shots row {row_num} drink"
            )
            row_warnings.extend(w)
            drink_type: DrinkType | None = DRINK_MAP.get(drink_key) if drink_key else None

            # Numeric fields
            dose_weight = parse_float(
                row.get("Dose Weight (g)", ""), context=f"shots row {row_num} dose"
            )
            extraction_time = parse_float(
                row.get("Brew Time (s)", ""), context=f"shots row {row_num} extraction"
            )
            final_weight = parse_float(
                row.get("Shot Weight (g)", ""), context=f"shots row {row_num} final_weight"
            )
            grinder_temp_before = parse_float(
                row.get("Pre Grinder Temp (F)", ""), context=f"shots row {row_num} temp_before"
            )
            grinder_temp_after = parse_float(
                row.get("Post Grinder Temp (F)", ""), context=f"shots row {row_num} temp_after"
            )

            # Pre-infusion
            pre_infusion = row.get("Pre-Infusion Time (s)", "").strip() or None

            # Grind setting + grinder inference
            grind_raw = row.get("Grinder Setting", "").strip()
            grind_setting = normalize_grind(grind_raw) if grind_raw else None
            grinder_key = infer_grinder_key(grind_setting or "")

            # Drink Weight -> optional note
            dw_note = parse_drink_weight(
                row.get("Drink Weight (g)", "").strip(),
                context=f"shots row {row_num} drink_weight",
            )

            # Combine notes: drink weight note first, then original notes
            orig_notes = row.get("Notes", "").strip() or None
            notes_parts = [p for p in [dw_note, orig_notes] if p]
            notes = "; ".join(notes_parts) if notes_parts else None

            shot: dict[str, Any] = {
                # Internal tracking (stripped before insert)
                "code": code,
                "_row": row_num,
                "_grinder_key": grinder_key,
                # Shot fields
                "date": date_val,
                "maker": maker,
                "drink_type": drink_type,
                "dose_weight": dose_weight,
                "pre_infusion_time": pre_infusion,
                "extraction_time": extraction_time,
                "final_weight": final_weight,
                "grind_setting": grind_setting,
                "grinder_temp_before": grinder_temp_before,
                "grinder_temp_after": grinder_temp_after,
                "notes": notes,
                # FK placeholders — resolved during import
                "coffee_id": None,
                "grinder_id": None,
                "device_id": None,
                "scale_id": None,
                # Technique flags — not in source data, default False
                "wedge": False,
                "shaker": False,
                "wdt": False,
                "flow_taper": False,
            }

            logger.info(
                "shots row %d: %s  code=%s  maker=%s  drink=%s  "
                "dose=%s  yield=%s  extr=%s  grind=%s  grinder=%s",
                row_num, date_val, code, maker, drink_type,
                dose_weight, final_weight, extraction_time, grind_setting,
                grinder_key or "none",
            )
            for warning in row_warnings:
                logger.warning("  %s", warning)

            shots.append(shot)

    return shots


# ---------------------------------------------------------------------------
# Equipment resolution
# ---------------------------------------------------------------------------

_MACHINE_CUTOVER = date(2026, 2, 19)  # ECM first used on this date; Breville before


def resolve_equipment(session: Any) -> dict[str, int | None]:
    """Look up grinder and brewing device IDs by name substring.

    Grinders: "mazzer", "baratza"
    Brewing devices: "breville" (used before 2026-02-19), "ecm" (on/after 2026-02-19)

    Args:
        session: SQLAlchemy session

    Returns:
        Dict with keys "mazzer", "baratza", "breville", "ecm"; values are DB IDs or None
    """
    result: dict[str, int | None] = {"mazzer": None, "baratza": None, "breville": None, "ecm": None}

    for grinder in session.query(Grinder).all():
        label = f"{grinder.make} {grinder.model}".lower()
        if "mazzer" in label and result["mazzer"] is None:
            result["mazzer"] = grinder.id
            logger.info("Equipment: Mazzer -> id=%d (%s %s)", grinder.id, grinder.make, grinder.model)
        elif "baratza" in label and result["baratza"] is None:
            result["baratza"] = grinder.id
            logger.info("Equipment: Baratza -> id=%d (%s %s)", grinder.id, grinder.make, grinder.model)

    for device in session.query(BrewingDevice).all():
        label = f"{device.make} {device.model}".lower()
        if "breville" in label and result["breville"] is None:
            result["breville"] = device.id
            logger.info("Equipment: Breville -> id=%d (%s %s)", device.id, device.make, device.model)
        if ("ecm" in label or "synchronika" in label) and result["ecm"] is None:
            result["ecm"] = device.id
            logger.info("Equipment: ECM -> id=%d (%s %s)", device.id, device.make, device.model)

    if result["mazzer"] is None:
        logger.warning("Equipment: Mazzer NOT FOUND in DB — grinder_id will be null for Mazzer shots")
    if result["baratza"] is None:
        logger.warning("Equipment: Baratza NOT FOUND in DB — grinder_id will be null for Baratza shots")
    if result["breville"] is None:
        logger.warning("Equipment: Breville NOT FOUND in DB — device_id will be null for pre-%s shots", _MACHINE_CUTOVER)
    if result["ecm"] is None:
        logger.warning("Equipment: ECM NOT FOUND in DB — device_id will be null for post-%s shots", _MACHINE_CUTOVER)

    return result


# ---------------------------------------------------------------------------
# Coffee deduplication
# ---------------------------------------------------------------------------

def _token_overlap(a: str, b: str) -> float:
    """Fraction of tokens in 'a' that appear in 'b' (case-insensitive)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def _fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    """Return True if 'a' and 'b' are similar enough by token overlap or edit distance.

    Tries token overlap first (> 0.5 is an immediate match). Falls back to
    SequenceMatcher ratio for single-word names or abbreviations (e.g.
    "Ollancay" vs "Ollancey", "Col." vs "Collective").

    Args:
        a:         Incoming string (from CSV)
        b:         Existing DB string
        threshold: SequenceMatcher ratio floor for the fallback path

    Returns:
        True if the strings are considered equivalent
    """
    if not a or not b:
        return False
    if _token_overlap(a, b) > 0.5:
        return True
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def find_existing_coffee(session: Any, coffee: dict[str, Any]) -> int | None:
    """Check whether a coffee already exists in the database.

    Matches on the same roast_date, then checks fuzzy similarity of both
    name and roaster using token overlap with a SequenceMatcher fallback.
    Name requires a higher similarity threshold (0.8) than roaster (0.5),
    since roaster names are frequently abbreviated in OCR output.

    Args:
        session: SQLAlchemy session
        coffee:  Parsed coffee dict

    Returns:
        Existing coffee ID if a confident match is found, else None
    """
    if not coffee.get("roast_date"):
        return None

    candidates = (
        session.query(Coffee)
        .filter(Coffee.roast_date == coffee["roast_date"])
        .all()
    )

    for c in candidates:
        name_score = _token_overlap(coffee.get("name", ""), c.name or "")
        roaster_score = _token_overlap(coffee.get("roaster", ""), c.roaster or "")
        name_ratio = SequenceMatcher(None, (coffee.get("name") or "").lower(), (c.name or "").lower()).ratio()
        roaster_ratio = SequenceMatcher(None, (coffee.get("roaster") or "").lower(), (c.roaster or "").lower()).ratio()

        name_match = _fuzzy_match(coffee.get("name", ""), c.name or "", threshold=0.8)
        roaster_match = _fuzzy_match(coffee.get("roaster", ""), c.roaster or "", threshold=0.5)

        logger.debug(
            "find_existing_coffee: comparing '%s'/'%s' vs existing id=%d '%s'/'%s' "
            "name_score=%.2f(ratio=%.2f) roaster_score=%.2f(ratio=%.2f)",
            coffee.get("name"), coffee.get("roaster"),
            c.id, c.name, c.roaster,
            name_score, name_ratio, roaster_score, roaster_ratio,
        )

        if name_match and roaster_match:
            logger.info(
                "Coffee '%s' roast_date=%s -> matched existing id=%d '%s' "
                "(name_overlap=%.0f%% name_ratio=%.0f%% roaster_overlap=%.0f%% roaster_ratio=%.0f%%) — skipping insert",
                coffee["name"], coffee["roast_date"],
                c.id, c.name,
                name_score * 100, name_ratio * 100,
                roaster_score * 100, roaster_ratio * 100,
            )
            return c.id

    return None


# ---------------------------------------------------------------------------
# Import orchestration
# ---------------------------------------------------------------------------

_INTERNAL_KEYS = {"code", "_row", "_grinder_key"}


def import_data(
    coffees: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    dry_run: bool,
    session: Any,
) -> None:
    """Insert parsed coffees and shots into the database.

    In dry-run mode, prints a formatted report of all records and decisions
    without writing anything. In real mode, wraps everything in a single
    transaction that rolls back on any error.

    Args:
        coffees:  Parsed coffee dicts from parse_coffees()
        shots:    Parsed shot dicts from parse_shots()
        dry_run:  If True, report only — no DB writes
        session:  SQLAlchemy session
    """
    equipment = resolve_equipment(session)

    # ------------------------------------------------------------------
    # Coffee pass: deduplicate, then insert or reuse
    # ------------------------------------------------------------------
    code_to_id: dict[str, int] = {}
    coffee_plan: list[tuple[str, dict[str, Any], str]] = []  # (code, dict, action)

    for c in coffees:
        code = c["code"]
        existing_id = find_existing_coffee(session, c)
        if existing_id is not None:
            code_to_id[code] = existing_id
            coffee_plan.append((code, c, f"EXISTING id={existing_id} (skip)"))
        else:
            coffee_plan.append((code, c, "INSERT"))

    if dry_run:
        # Build a synthetic code map so shot display shows code→coffee correctly.
        # Codes with existing IDs are already set; codes marked INSERT get placeholder -1.
        for code, _c, action in coffee_plan:
            if code not in code_to_id:
                code_to_id[code] = -1  # will be assigned on real insert

        print("\n=== DRY RUN — no data will be written ===\n")
        print(f"COFFEES ({len(coffees)} records)")
        for code, c, action in coffee_plan:
            print(
                f"  {code} | {c.get('roaster')} | {c.get('name')} "
                f"| {c.get('roast_level')} | {c.get('roast_date')}  ->  {action}"
            )
    else:
        for code, c, action in coffee_plan:
            if "INSERT" in action:
                fields = {k: v for k, v in c.items() if k not in _INTERNAL_KEYS}
                db_coffee = Coffee(**fields)
                session.add(db_coffee)
                session.flush()  # get ID without committing
                code_to_id[code] = db_coffee.id
                logger.info("Inserted coffee code=%s -> id=%d", code, db_coffee.id)

    # ------------------------------------------------------------------
    # Shot pass
    # ------------------------------------------------------------------
    if dry_run:
        print(f"\nSHOTS ({len(shots)} records)")

    inserted_shots = 0
    for s in shots:
        code = s["code"]
        row_num = s["_row"]
        grinder_key = s["_grinder_key"]

        coffee_id = code_to_id.get(code)
        if coffee_id is None and not dry_run:
            logger.warning(
                "shots row %d: code=%s has no matching coffee — coffee_id will be null",
                row_num, code,
            )

        grinder_id = equipment.get(grinder_key) if grinder_key else None

        # Assign device by date: Breville before cutover, ECM on/after
        shot_date: date | None = s.get("date")
        if shot_date is not None:
            device_key = "breville" if shot_date < _MACHINE_CUTOVER else "ecm"
            device_id = equipment.get(device_key)
        else:
            device_key = None
            device_id = None

        if dry_run:
            grind_info = s.get("grind_setting") or "—"
            grinder_info = (
                f"{grinder_key}(id={grinder_id})" if grinder_id
                else (f"{grinder_key}(NOT IN DB)" if grinder_key else "none")
            )
            device_info = (
                f"{device_key}(id={device_id})" if device_id
                else (f"{device_key}(NOT IN DB)" if device_key else "none")
            )
            coffee_ref = (
                f"{code}(id={coffee_id})" if coffee_id and coffee_id > 0
                else f"{code}(TBD)"
            )
            print(
                f"  row {row_num:>2} | {s['date']} | coffee={coffee_ref} | maker={s['maker']} "
                f"| drink={s.get('drink_type') or '—'} | dose={s.get('dose_weight') or '—'} "
                f"| yield={s.get('final_weight') or '—'} | extr={s.get('extraction_time') or '—'}s "
                f"| grind={grind_info} | grinder={grinder_info} | device={device_info}"
            )
            if s.get("notes"):
                print(f"         notes: {s['notes']}")
        else:
            fields = {
                k: v for k, v in s.items() if k not in _INTERNAL_KEYS
            }
            fields["coffee_id"] = coffee_id
            fields["grinder_id"] = grinder_id
            fields["device_id"] = device_id
            db_shot = Shot(**fields)
            session.add(db_shot)
            inserted_shots += 1
            logger.info(
                "Inserted shot row=%d: %s %s coffee_id=%s grinder=%s",
                row_num, s["date"], s["maker"], coffee_id, grinder_key,
            )

    if dry_run:
        inserted_coffees = sum(1 for _, _, a in coffee_plan if "INSERT" in a)
        skipped_coffees = len(coffees) - inserted_coffees
        print(
            f"\nSUMMARY (dry run)\n"
            f"  Coffees: {inserted_coffees} to insert, {skipped_coffees} already exist\n"
            f"  Shots:   {len(shots)} to insert\n"
        )
        print("Re-run without --dry-run to write to the database.")
    else:
        session.commit()
        inserted_coffees = sum(1 for _, _, a in coffee_plan if "INSERT" in a)
        logger.info(
            "Done. Inserted %d coffee(s) (%d already existed) and %d shot(s).",
            inserted_coffees,
            len(coffees) - inserted_coffees,
            inserted_shots,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and run the import."""
    parser = argparse.ArgumentParser(
        description="Import OCR-processed coffee shot CSV data into the database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  poetry run python bin/import_ocr_data.py --dry-run --verbose\n"
            "  poetry run python bin/import_ocr_data.py\n"
            "  poetry run python bin/import_ocr_data.py --input-dir import_data/2/files\n"
        ),
    )
    parser.add_argument(
        "--input-dir",
        default="import_data/1/files",
        help="Directory containing the CSV files (default: import_data/1/files)",
    )
    parser.add_argument(
        "--coffees-file",
        default="coffee_roasters.csv",
        help="Filename of the coffee definitions CSV (default: coffee_roasters.csv)",
    )
    parser.add_argument(
        "--shots-file",
        default="coffee_shots.csv",
        help="Filename of the shots CSV (default: coffee_shots.csv)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Year to use for all dates (default: 2026)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display what would be imported without writing to the database",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging for every field decision",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    input_dir = Path(args.input_dir)
    coffees_path = input_dir / args.coffees_file
    shots_path = input_dir / args.shots_file

    for p in (coffees_path, shots_path):
        if not p.exists():
            logger.error("File not found: %s", p)
            sys.exit(1)

    logger.info("Parsing coffees from %s", coffees_path)
    coffees = parse_coffees(coffees_path, args.year)
    logger.info("Parsed %d coffee record(s)", len(coffees))

    logger.info("Parsing shots from %s", shots_path)
    shots = parse_shots(shots_path, args.year)
    logger.info("Parsed %d shot record(s)", len(shots))

    config = load_config()
    init_db(config.database.get_url(), pool_size=1)
    session = get_session()

    try:
        import_data(coffees, shots, dry_run=args.dry_run, session=session)
    except Exception:
        if not args.dry_run:
            session.rollback()
            logger.exception("Import failed — all changes rolled back")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
