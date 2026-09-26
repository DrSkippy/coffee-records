"""Fuzzy string matching helpers for coffees and equipment."""

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

# Words too generic to identify a piece of equipment on their own.
_EQUIPMENT_STOPWORDS = frozenset({"coffee", "espresso", "grinder", "machine", "the"})


def token_overlap(a: str, b: str) -> float:
    """Fraction of whitespace tokens in ``a`` that appear in ``b`` (case-insensitive).

    Args:
        a: Incoming string.
        b: Existing string to compare against.

    Returns:
        Overlap fraction in [0, 1]; 0 when ``a`` has no tokens.
    """
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    """Return True if ``a`` and ``b`` are similar by token overlap or edit distance.

    Tries token overlap first (> 0.5 is an immediate match). Falls back to
    SequenceMatcher ratio for single-word names or abbreviations (e.g.
    "Ollancay" vs "Ollancey", "Col." vs "Collective").

    Args:
        a: Incoming string.
        b: Existing string.
        threshold: SequenceMatcher ratio floor for the fallback path.

    Returns:
        True if the strings are considered equivalent.
    """
    if not a or not b:
        return False
    if token_overlap(a, b) > 0.5:
        return True
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def normalize_tokens(text: str) -> set[str]:
    """Lowercase ``text`` and split on any non-alphanumeric run.

    Treats "Option-O" and "Option O" as the same tokens.

    Args:
        text: Free-form label.

    Returns:
        Set of non-empty lowercase tokens.
    """
    return {t for t in re.split(r"[^0-9a-z]+", text.lower()) if t}


def best_equipment_match(
    label: str, candidates: Iterable[tuple[int, str]], min_overlap: float = 0.5
) -> int | None:
    """Pick the candidate whose label best overlaps ``label``.

    Overlap is measured symmetrically as shared tokens divided by the smaller
    token set, so "ECM Synchronika II" matches "ECM ECM Synchronika II
    Espresso Machine".

    Args:
        label: Incoming equipment description (e.g. brand + name + model).
        candidates: ``(id, "make model")`` pairs from the database.
        min_overlap: Score that must be exceeded to count as a match.

    Returns:
        The best candidate id, or None when nothing exceeds ``min_overlap``.
    """
    wanted = normalize_tokens(label) - _EQUIPMENT_STOPWORDS
    if not wanted:
        return None
    best_id: int | None = None
    best_score = min_overlap
    for candidate_id, candidate_label in candidates:
        have = normalize_tokens(candidate_label) - _EQUIPMENT_STOPWORDS
        if not have:
            continue
        score = len(wanted & have) / min(len(wanted), len(have))
        if score > best_score:
            best_id, best_score = candidate_id, score
    return best_id
