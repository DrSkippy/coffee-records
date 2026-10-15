#!/usr/bin/env python
"""Import OCR-processed CSV data into the coffee-records database.

Parses two CSVs produced by an OCR app from handwritten shot log sheets:
  - coffee_roasters.csv  : coffee bag definitions
  - coffee_shots.csv     : individual shot records

The OCR encodes a circled choice by wrapping it in parentheses or replacing the
first character with "0". Position (1-based) is the primary signal; letters are
logged as secondary confirmation.

Sheet-specific settings (year, machine cutover date, brewer initials,
equipment keywords) live in ocr_import.yaml.

Usage:
    poetry run python bin/import_ocr_data.py --dry-run --verbose
    poetry run python bin/import_ocr_data.py
"""

import argparse
import csv
import enum
import logging
import re
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from coffee_records.config import MatchingConfig, load_config  # noqa: E402
from coffee_records.database import get_session, init_db  # noqa: E402
from coffee_records.models.coffee import Coffee, RoastLevel  # noqa: E402
from coffee_records.models.equipment import BrewingDevice, Grinder  # noqa: E402
from coffee_records.models.shot import DrinkType, Shot  # noqa: E402
from coffee_records.services.matching import (  # noqa: E402
    is_same_beans,
    token_overlap,
)

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_PATH = Path(__file__).parent.parent / "ocr_import.yaml"


# ---------------------------------------------------------------------------
# Settings and record types
# ---------------------------------------------------------------------------


class EquipmentKey(str, enum.Enum):
    """Equipment the log sheets refer to."""

    mazzer = "mazzer"
    baratza = "baratza"
    breville = "breville"
    ecm = "ecm"


GRINDER_KEYS = (EquipmentKey.mazzer, EquipmentKey.baratza)
DEVICE_KEYS = (EquipmentKey.breville, EquipmentKey.ecm)


class OcrImportSettings(BaseModel):
    """Sheet-specific import settings loaded from ocr_import.yaml."""

    year: int = 2026
    machine_cutover: date = date(2026, 2, 19)
    drink_weight_grams: tuple[int, int] = (40, 500)
    unknown_maker: str = "Unknown"
    brewers: dict[str, str] = {"sc": "Scott", "sa": "Sara", "ot": "Other"}
    equipment_keywords: dict[EquipmentKey, list[str]] = {
        EquipmentKey.mazzer: ["mazzer"],
        EquipmentKey.baratza: ["baratza"],
        EquipmentKey.breville: ["breville"],
        EquipmentKey.ecm: ["ecm", "synchronika"],
    }


def load_settings(path: Path) -> OcrImportSettings:
    """Load import settings from YAML (defaults when the file is absent).

    Args:
        path: Settings file.

    Returns:
        Validated settings.
    """
    if not path.exists():
        return OcrImportSettings()
    with path.open() as f:
        return OcrImportSettings.model_validate(yaml.safe_load(f) or {})


@dataclass
class ParsedCoffee:
    """A coffee bag row from coffee_roasters.csv."""

    code: str
    name: str
    roaster: str
    origin_country: str | None
    variety: str | None
    process: str | None
    roast_level: RoastLevel | None
    roast_date: date | None

    def model_fields(self) -> dict[str, object]:
        """Return the Coffee model column values (without the sheet code)."""
        fields = asdict(self)
        del fields["code"]
        return fields


@dataclass
class ParsedShot:
    """A shot row from coffee_shots.csv.

    ``code`` links the shot to a coffee bag and ``row`` / ``grinder_key`` are
    import bookkeeping; the rest are Shot model fields.
    """

    code: str
    row: int
    grinder_key: EquipmentKey | None
    date: date
    maker: str
    drink_type: DrinkType | None
    dose_weight: float | None
    pre_infusion_time: str | None
    extraction_time: float | None
    final_weight: float | None
    grind_setting: str | None
    grinder_temp_before: float | None
    grinder_temp_after: float | None
    notes: str | None


class CoffeeAction(enum.Enum):
    """What the import will do with a parsed coffee."""

    INSERT = "INSERT"
    EXISTING = "EXISTING"


@dataclass
class CoffeePlan:
    """Planned action for one parsed coffee."""

    coffee: ParsedCoffee
    action: CoffeeAction
    existing_id: int | None = None

    def describe(self) -> str:
        """Return the dry-run label for this plan."""
        if self.action is CoffeeAction.EXISTING:
            return f"EXISTING id={self.existing_id} (skip)"
        return "INSERT"


@dataclass
class EquipmentIds:
    """Database ids for the equipment named on the sheets (None if absent)."""

    ids: dict[EquipmentKey, int | None] = field(
        default_factory=lambda: {key: None for key in EquipmentKey}
    )


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
        pos = len(re.findall(r"\S+", before))

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
            context,
            raw,
            token,
            pos + 1,
            expected,
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
                context,
                raw,
                tok,
                i + 1,
                expected,
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


def parse_date(raw: str, year: int) -> date | None:
    """Parse an M/D string into a date using the given year.

    Args:
        raw:  Date string like "3/1" or "2/16"
        year: Year to apply

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
    # Strip trailing non-numeric garbage (e.g. "40.k" -> "40.", OCR artifact)
    cleaned = re.sub(r"[^\d.]+$", "", cleaned)
    if not cleaned or cleaned == ".":
        return None
    try:
        val = float(cleaned)
    except ValueError:
        logger.debug("parse_float [%s]: cannot parse %r", context, raw)
        return None
    if context:
        logger.debug("parse_float [%s]: %r -> %g", context, raw, val)
    return val


def parse_drink_weight(
    raw: str, valid_range: tuple[int, int], context: str = ""
) -> str | None:
    """Parse the Drink Weight column into a note string.

    Rules:
      - "x" or "X" (stripped, case-insensitive) -> "shot rejected"
      - First extracted integer within ``valid_range`` -> "drink weight: {n}g"
      - Otherwise -> None (discard)

    Args:
        raw:         Raw drink weight string
        valid_range: Inclusive (low, high) plausible drink weight in grams
        context:     Description for log messages

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
    if not nums:
        logger.debug(
            "parse_drink_weight [%s]: %r -> no numeric content, discarding",
            context,
            raw,
        )
        return None

    grams = int(nums[0])
    low, high = valid_range
    if low <= grams <= high:
        logger.debug(
            "parse_drink_weight [%s]: %r -> drink weight %dg", context, raw, grams
        )
        return f"drink weight: {grams}g"
    logger.debug(
        "parse_drink_weight [%s]: %r -> %d out of range [%d, %d], discarding",
        context,
        raw,
        grams,
        low,
        high,
    )
    return None


def normalize_grind(raw: str) -> str:
    """Normalize a grind setting string.

    Replaces Unicode fraction ½ with "1/2" and strips surrounding whitespace.

    Args:
        raw: Raw grind setting

    Returns:
        Normalized string
    """
    return raw.strip().replace("½", "1/2")


def infer_grinder_key(grind_setting: str) -> EquipmentKey | None:
    """Infer which grinder was used from the grind setting format.

    Rules:
      - Contains "+" (e.g. "8+7", "8+7 1/2") -> mazzer
      - Plain integer or decimal (e.g. "19.5")  -> baratza
      - Anything else                            -> None

    Args:
        grind_setting: Normalized grind setting string

    Returns:
        EquipmentKey.mazzer, EquipmentKey.baratza, or None
    """
    if not grind_setting:
        return None
    if "+" in grind_setting:
        logger.debug("infer_grinder: %r contains '+' -> mazzer", grind_setting)
        return EquipmentKey.mazzer
    if re.match(r"^\d+(\.\d+)?$", grind_setting):
        logger.debug("infer_grinder: %r is numeric -> baratza", grind_setting)
        return EquipmentKey.baratza
    logger.debug(
        "infer_grinder: %r -> unrecognized pattern, no grinder inferred", grind_setting
    )
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


def _read_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(sheet row number, row)`` for rows with a Code.

    Args:
        path: CSV file.

    Yields:
        Spreadsheet row number (header is row 1) and the row dict.
    """
    with path.open(newline="", encoding="utf-8") as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):
            if row.get("Code", "").strip():
                yield row_num, row


def _cell(row: dict[str, str], column: str) -> str:
    """Return a stripped cell value ("" when missing)."""
    return (row.get(column) or "").strip()


def _log_warnings(warnings: list[str]) -> None:
    """Log each collected row warning."""
    for warning in warnings:
        logger.warning("  %s", warning)


def parse_coffees(path: Path, year: int) -> list[ParsedCoffee]:
    """Parse the coffee_roasters.csv file.

    Args:
        path: Path to the CSV file
        year: Year to apply to roast dates

    Returns:
        Parsed coffee bags
    """
    coffees: list[ParsedCoffee] = []
    for row_num, row in _read_rows(path):
        code = _cell(row, "Code")
        roaster = _cell(row, "Coffee Roaster")
        name = _cell(row, "Coffee Name")
        if not roaster and not name:
            logger.info(
                "coffees row %d (code=%s): all fields empty — skipping", row_num, code
            )
            continue

        _, roast_key, row_warnings = parse_circled(
            _cell(row, "Roast"), ROAST_OPTIONS, context=f"coffees row {row_num} roast"
        )
        coffee = ParsedCoffee(
            code=code,
            name=name,
            roaster=roaster,
            origin_country=_cell(row, "Coffee Origin") or None,
            variety=_cell(row, "Variety") or None,
            process=_cell(row, "Process") or None,
            roast_level=ROAST_MAP.get(roast_key) if roast_key else None,
            roast_date=parse_date(_cell(row, "Roast Date"), year),
        )
        logger.info(
            "coffees row %d: code=%s  %s / %s  roast=%s  date=%s",
            row_num,
            code,
            roaster,
            name,
            coffee.roast_level,
            coffee.roast_date,
        )
        _log_warnings(row_warnings)
        coffees.append(coffee)
    return coffees


def _parse_shot_row(
    row_num: int, row: dict[str, str], settings: OcrImportSettings
) -> ParsedShot | None:
    """Parse one shots CSV row.

    Args:
        row_num: Spreadsheet row number.
        row: CSV row.
        settings: Import settings.

    Returns:
        The parsed shot, or None when the row has no valid Brew Date.
    """
    # Date (required)
    shot_date = parse_date(_cell(row, "Brew Date"), settings.year)
    if shot_date is None:
        logger.warning(
            "shots row %d: missing/invalid Brew Date — skipping row", row_num
        )
        return None

    def context(name: str) -> str:
        return f"shots row {row_num} {name}"

    row_warnings: list[str] = []

    # Brew method (logged only, not stored in DB)
    _, method_key, warnings = parse_circled(
        _cell(row, "Brew Method"), BREW_METHOD_OPTIONS, context=context("brew_method")
    )
    row_warnings.extend(warnings)
    logger.debug(
        "shots row %d: brew_method=%s",
        row_num,
        BREW_METHOD_LABELS.get(method_key or "", "unknown"),
    )

    # Brewer -> maker
    brewer_raw = _cell(row, "Brewer")
    _, brewer_key, warnings = parse_circled(
        brewer_raw, list(settings.brewers), context=context("brewer")
    )
    row_warnings.extend(warnings)
    if brewer_key is not None:
        maker = settings.brewers[brewer_key]
    else:
        maker = settings.unknown_maker
        row_warnings.append(
            f"shots row {row_num}: could not decode brewer from {brewer_raw!r} "
            f"— using '{maker}'"
        )

    # Drink type
    _, drink_key, warnings = parse_circled(
        _cell(row, "Drink"), DRINK_OPTIONS, context=context("drink")
    )
    row_warnings.extend(warnings)

    # Grind setting + grinder inference
    grind_raw = _cell(row, "Grinder Setting")
    grind_setting = normalize_grind(grind_raw) if grind_raw else None

    # Combine notes: drink weight note first, then original notes
    drink_weight_note = parse_drink_weight(
        _cell(row, "Drink Weight (g)"),
        settings.drink_weight_grams,
        context=context("drink_weight"),
    )
    notes_parts = [p for p in (drink_weight_note, _cell(row, "Notes")) if p]

    shot = ParsedShot(
        code=_cell(row, "Code"),
        row=row_num,
        grinder_key=infer_grinder_key(grind_setting or ""),
        date=shot_date,
        maker=maker,
        drink_type=DRINK_MAP.get(drink_key) if drink_key else None,
        dose_weight=parse_float(row.get("Dose Weight (g)", ""), context("dose")),
        pre_infusion_time=_cell(row, "Pre-Infusion Time (s)") or None,
        extraction_time=parse_float(
            row.get("Brew Time (s)", ""), context("extraction")
        ),
        final_weight=parse_float(
            row.get("Shot Weight (g)", ""), context("final_weight")
        ),
        grind_setting=grind_setting,
        grinder_temp_before=parse_float(
            row.get("Pre Grinder Temp (F)", ""), context("temp_before")
        ),
        grinder_temp_after=parse_float(
            row.get("Post Grinder Temp (F)", ""), context("temp_after")
        ),
        notes="; ".join(notes_parts) if notes_parts else None,
    )
    logger.info(
        "shots row %d: %s  code=%s  maker=%s  drink=%s  "
        "dose=%s  yield=%s  extr=%s  grind=%s  grinder=%s",
        row_num,
        shot.date,
        shot.code,
        shot.maker,
        shot.drink_type,
        shot.dose_weight,
        shot.final_weight,
        shot.extraction_time,
        shot.grind_setting,
        shot.grinder_key.value if shot.grinder_key else "none",
    )
    _log_warnings(row_warnings)
    return shot


def parse_shots(path: Path, settings: OcrImportSettings) -> list[ParsedShot]:
    """Parse the coffee_shots.csv file.

    Args:
        path: Path to the CSV file
        settings: Import settings (year, brewers, drink weight range)

    Returns:
        Parsed shots (rows without a valid date are skipped)
    """
    return [
        shot
        for row_num, row in _read_rows(path)
        if (shot := _parse_shot_row(row_num, row, settings)) is not None
    ]


# ---------------------------------------------------------------------------
# Equipment resolution
# ---------------------------------------------------------------------------


def _first_matching(labelled: list[tuple[int, str]], keywords: list[str]) -> int | None:
    """Return the first id whose lowercase label contains any keyword."""
    return next(
        (pk for pk, label in labelled if any(k in label for k in keywords)), None
    )


def resolve_equipment(session: Session, settings: OcrImportSettings) -> EquipmentIds:
    """Look up grinder and brewing device IDs by name substring.

    Grinders: mazzer, baratza. Brewing devices: breville (used before the
    machine cutover date), ecm (on/after it).

    Args:
        session: SQLAlchemy session
        settings: Supplies the keywords and cutover date (for log messages)

    Returns:
        Database id (or None) for each EquipmentKey
    """
    grinders = [(g.id, f"{g.make} {g.model}".lower()) for g in session.query(Grinder)]
    devices = [
        (d.id, f"{d.make} {d.model}".lower()) for d in session.query(BrewingDevice)
    ]
    equipment = EquipmentIds()
    for key in EquipmentKey:
        candidates = grinders if key in GRINDER_KEYS else devices
        pk = _first_matching(candidates, settings.equipment_keywords.get(key, []))
        equipment.ids[key] = pk
        if pk is not None:
            logger.info("Equipment: %s -> id=%d", key.value, pk)
        elif key in GRINDER_KEYS:
            logger.warning(
                "Equipment: %s NOT FOUND in DB — grinder_id will be null for its shots",
                key.value,
            )
        else:
            side = "pre" if key is EquipmentKey.breville else "post"
            logger.warning(
                "Equipment: %s NOT FOUND in DB — device_id will be null for %s-%s shots",
                key.value,
                side,
                settings.machine_cutover,
            )
    return equipment


def device_key_for(shot_date: date, cutover: date) -> EquipmentKey:
    """Return the espresso machine in use on a date.

    Args:
        shot_date: Shot date.
        cutover: First day the ECM was used.

    Returns:
        Breville before the cutover, ECM on/after.
    """
    return EquipmentKey.breville if shot_date < cutover else EquipmentKey.ecm


# ---------------------------------------------------------------------------
# Coffee deduplication
# ---------------------------------------------------------------------------


def find_existing_coffee(
    session: Session, coffee: ParsedCoffee, matching: MatchingConfig | None = None
) -> int | None:
    """Check whether a coffee already exists in the database.

    Matches on the same roast_date, then checks fuzzy similarity of both
    name and roaster using token overlap with a SequenceMatcher fallback.
    Name requires a higher similarity threshold than roaster, since roaster
    names are frequently abbreviated in OCR output.

    Args:
        session:  SQLAlchemy session
        coffee:   Parsed coffee
        matching: Similarity thresholds

    Returns:
        Existing coffee ID if a confident match is found, else None
    """
    if coffee.roast_date is None or not coffee.roaster:
        return None

    candidates = (
        session.query(Coffee).filter(Coffee.roast_date == coffee.roast_date).all()
    )
    for candidate in candidates:
        name_score = token_overlap(coffee.name, candidate.name or "")
        name_ratio = SequenceMatcher(
            None, coffee.name.lower(), (candidate.name or "").lower()
        ).ratio()
        roaster_score = token_overlap(coffee.roaster, candidate.roaster or "")
        roaster_ratio = SequenceMatcher(
            None, coffee.roaster.lower(), (candidate.roaster or "").lower()
        ).ratio()
        logger.debug(
            "find_existing_coffee: comparing '%s'/'%s' vs existing id=%d '%s'/'%s' "
            "name_score=%.2f(ratio=%.2f) roaster_score=%.2f(ratio=%.2f)",
            coffee.name,
            coffee.roaster,
            candidate.id,
            candidate.name,
            candidate.roaster,
            name_score,
            name_ratio,
            roaster_score,
            roaster_ratio,
        )
        if is_same_beans(
            coffee.name,
            coffee.roaster,
            candidate.name or "",
            candidate.roaster or "",
            matching,
        ):
            logger.info(
                "Coffee '%s' roast_date=%s -> matched existing id=%d '%s' "
                "(name_overlap=%.0f%% name_ratio=%.0f%% roaster_overlap=%.0f%% "
                "roaster_ratio=%.0f%%) — skipping insert",
                coffee.name,
                coffee.roast_date,
                candidate.id,
                candidate.name,
                name_score * 100,
                name_ratio * 100,
                roaster_score * 100,
                roaster_ratio * 100,
            )
            return int(candidate.id)
    return None


# ---------------------------------------------------------------------------
# Import orchestration
# ---------------------------------------------------------------------------


def plan_coffees(
    session: Session, coffees: list[ParsedCoffee], matching: MatchingConfig
) -> list[CoffeePlan]:
    """Decide, per parsed coffee, whether to insert it or reuse an existing row.

    Args:
        session: SQLAlchemy session
        coffees: Parsed coffees
        matching: Similarity thresholds

    Returns:
        One plan per coffee
    """
    plans = []
    for coffee in coffees:
        existing_id = find_existing_coffee(session, coffee, matching)
        action = CoffeeAction.INSERT if existing_id is None else CoffeeAction.EXISTING
        plans.append(CoffeePlan(coffee, action, existing_id))
    return plans


def _equipment_label(key: EquipmentKey | None, pk: int | None) -> str:
    """Render ``key(id=N)``, ``key(NOT IN DB)`` or ``none`` for the dry-run report."""
    if pk:
        return f"{key.value if key else '?'}(id={pk})"
    return f"{key.value}(NOT IN DB)" if key else "none"


def report_dry_run(
    plans: list[CoffeePlan],
    shots: list[ParsedShot],
    equipment: EquipmentIds,
    cutover: date,
) -> None:
    """Log a formatted report of everything the import would do.

    Args:
        plans: Coffee plans
        shots: Parsed shots
        equipment: Resolved equipment ids
        cutover: Machine cutover date
    """
    code_to_id = {p.coffee.code: p.existing_id for p in plans}
    logger.info("=== DRY RUN — no data will be written ===")
    logger.info("COFFEES (%d records)", len(plans))
    for plan in plans:
        c = plan.coffee
        logger.info(
            "  %s | %s | %s | %s | %s  ->  %s",
            c.code,
            c.roaster,
            c.name,
            c.roast_level,
            c.roast_date,
            plan.describe(),
        )

    logger.info("SHOTS (%d records)", len(shots))
    for s in shots:
        device_key = device_key_for(s.date, cutover)
        coffee_id = code_to_id.get(s.code)
        coffee_ref = f"{s.code}(id={coffee_id})" if coffee_id else f"{s.code}(TBD)"
        grinder_id = equipment.ids[s.grinder_key] if s.grinder_key else None
        logger.info(
            "  row %2d | %s | coffee=%s | maker=%s | drink=%s | dose=%s | yield=%s "
            "| extr=%ss | grind=%s | grinder=%s | device=%s",
            s.row,
            s.date,
            coffee_ref,
            s.maker,
            s.drink_type or "—",
            s.dose_weight or "—",
            s.final_weight or "—",
            s.extraction_time or "—",
            s.grind_setting or "—",
            _equipment_label(s.grinder_key, grinder_id),
            _equipment_label(device_key, equipment.ids[device_key]),
        )
        if s.notes:
            logger.info("         notes: %s", s.notes)

    to_insert = sum(p.action is CoffeeAction.INSERT for p in plans)
    logger.info(
        "SUMMARY (dry run): coffees %d to insert, %d already exist; shots %d to insert",
        to_insert,
        len(plans) - to_insert,
        len(shots),
    )
    logger.info("Re-run without --dry-run to write to the database.")


def apply_import(
    session: Session,
    plans: list[CoffeePlan],
    shots: list[ParsedShot],
    equipment: EquipmentIds,
    cutover: date,
) -> None:
    """Insert planned coffees and all shots in a single transaction.

    Args:
        session: SQLAlchemy session (committed on success)
        plans: Coffee plans
        shots: Parsed shots
        equipment: Resolved equipment ids
        cutover: Machine cutover date
    """
    code_to_id: dict[str, int] = {}
    for plan in plans:
        if plan.action is CoffeeAction.EXISTING and plan.existing_id is not None:
            code_to_id[plan.coffee.code] = plan.existing_id
            continue
        db_coffee = Coffee(**plan.coffee.model_fields())
        session.add(db_coffee)
        session.flush()  # get ID without committing
        code_to_id[plan.coffee.code] = db_coffee.id
        logger.info("Inserted coffee code=%s -> id=%d", plan.coffee.code, db_coffee.id)

    for s in shots:
        coffee_id = code_to_id.get(s.code)
        if coffee_id is None:
            logger.warning(
                "shots row %d: code=%s has no matching coffee — coffee_id will be null",
                s.row,
                s.code,
            )
        session.add(
            Shot(
                date=s.date,
                maker=s.maker,
                drink_type=s.drink_type,
                dose_weight=s.dose_weight,
                pre_infusion_time=s.pre_infusion_time,
                extraction_time=s.extraction_time,
                final_weight=s.final_weight,
                grind_setting=s.grind_setting,
                grinder_temp_before=s.grinder_temp_before,
                grinder_temp_after=s.grinder_temp_after,
                notes=s.notes,
                coffee_id=coffee_id,
                grinder_id=equipment.ids[s.grinder_key] if s.grinder_key else None,
                device_id=equipment.ids[device_key_for(s.date, cutover)],
                # Technique flags — not in source data
                wedge=False,
                shaker=False,
                wdt=False,
                flow_taper=False,
            )
        )
        logger.info(
            "Inserted shot row=%d: %s %s coffee_id=%s grinder=%s",
            s.row,
            s.date,
            s.maker,
            coffee_id,
            s.grinder_key.value if s.grinder_key else None,
        )

    session.commit()
    inserted = sum(p.action is CoffeeAction.INSERT for p in plans)
    logger.info(
        "Done. Inserted %d coffee(s) (%d already existed) and %d shot(s).",
        inserted,
        len(plans) - inserted,
        len(shots),
    )


def import_data(
    coffees: list[ParsedCoffee],
    shots: list[ParsedShot],
    dry_run: bool,
    session: Session,
    settings: OcrImportSettings,
    matching: MatchingConfig | None = None,
) -> None:
    """Insert parsed coffees and shots, or report what would be inserted.

    Args:
        coffees:  Parsed coffees from parse_coffees()
        shots:    Parsed shots from parse_shots()
        dry_run:  If True, report only — no DB writes
        session:  SQLAlchemy session
        settings: Import settings
        matching: Similarity thresholds for coffee deduplication
    """
    equipment = resolve_equipment(session, settings)
    plans = plan_coffees(session, coffees, matching or MatchingConfig())
    if dry_run:
        report_dry_run(plans, shots, equipment, settings.machine_cutover)
    else:
        apply_import(session, plans, shots, equipment, settings.machine_cutover)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
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
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Sheet settings YAML (default: ocr_import.yaml)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year to use for all dates (overrides the settings file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display what would be imported without writing to the database",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging for every field decision",
    )
    return parser


def main() -> None:
    """Parse arguments and run the import."""
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    settings = load_settings(args.settings)
    if args.year is not None:
        settings = settings.model_copy(update={"year": args.year})

    input_dir = Path(args.input_dir)
    coffees_path = input_dir / args.coffees_file
    shots_path = input_dir / args.shots_file
    for path in (coffees_path, shots_path):
        if not path.exists():
            logger.error("File not found: %s", path)
            sys.exit(1)

    logger.info("Parsing coffees from %s", coffees_path)
    coffees = parse_coffees(coffees_path, settings.year)
    logger.info("Parsed %d coffee record(s)", len(coffees))

    logger.info("Parsing shots from %s", shots_path)
    shots = parse_shots(shots_path, settings)
    logger.info("Parsed %d shot record(s)", len(shots))

    config = load_config()
    init_db(config.database.get_url(), pool_size=1)
    session = get_session()
    try:
        import_data(
            coffees,
            shots,
            dry_run=args.dry_run,
            session=session,
            settings=settings,
            matching=config.matching,
        )
    except Exception:
        session.rollback()
        logger.exception(
            "Import failed%s", "" if args.dry_run else " — all changes rolled back"
        )
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
