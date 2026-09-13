"""
candidates.py

Step 6 — Constrained counterfactual interpretation generation.

Given an uncertain field and its source OCR token, produce a SMALL set of
plausible alternative interpretations, constrained by:

    1. OCR confusion patterns (visually similar characters: 0/O, 1/l, 5/S, ...)
    2. Format rules (money has 2 decimals; dates have day/month/year)
    3. Structural plausibility (reject nonsense)

Output: list of dicts, one per candidate interpretation:

    {"value": <field-typed value>, "reason": "<short label>", "weight": <0-1>}

Weights reflect how plausible a candidate is:
    1.0   -- the original OCR interpretation (as-is)
    0.5-0.8 -- format reinterpretation (comma vs dot; day/month swap)
    0.3-0.5 -- single character confusion

Text fields (company, address) get only the as-is candidate in this version
because they do not enter the decision function. If the decision rule
later uses them, extend the text branch.
"""

import itertools
import re


# ---------------------------------------------------------
# OCR confusion patterns
# ---------------------------------------------------------

# Pairs of characters that OCR commonly confuses.
CONFUSION_PAIRS = [
    ("0", "O"),
    ("0", "o"),
    ("1", "l"),
    ("1", "I"),
    ("5", "S"),
    ("5", "s"),
    ("8", "B"),
    ("6", "G"),
    ("2", "Z"),
    (",", "."),
    (".", ","),
    ("m", "rn"),
    ("rn", "m"),
]


# ---------------------------------------------------------
# Money candidates
# ---------------------------------------------------------

def _money_candidates(source_token: str) -> list:
    """
    Generate plausible interpretations of an uncertain money token.

    Examples:
        "9,00"   -> 9.0, 900.0, 9.90
        "1.500"  -> 1.50, 1500.0
        "9.00"   -> 9.0 (unambiguous; only as-is)
    """
    token = source_token.strip()
    candidates = []

    # As-is interpretation via normalize_money (imported lazily to avoid cycle)
    from src.field_extractor import normalize_money

    def _add(value, reason, weight):
        if value is None:
            return
        # Deduplicate by value
        for c in candidates:
            if c["value"] == value:
                return
        candidates.append({"value": value, "reason": reason, "weight": weight})

    # 1. As-is
    _add(normalize_money(token), "as_is", 1.0)

    # 2. Separator reinterpretations
    if "," in token and "." not in token:
        # "9,00" -> 900 (comma treated as thousands separator)
        stripped = token.replace(",", "")
        _add(normalize_money(stripped), "comma_as_thousands", 0.4)

    if "." in token and "," not in token:
        # "9.00" -> 900 (dot treated as thousands separator)
        stripped = token.replace(".", "")
        _add(normalize_money(stripped), "dot_as_thousands", 0.3)

    # 3. Single character confusions in digit positions
    for i, ch in enumerate(token):
        for a, b in CONFUSION_PAIRS:
            if ch == a:
                swapped = token[:i] + b + token[i+1:]
                _add(normalize_money(swapped),
                     f"confusion_{a}_to_{b}_at_{i}", 0.35)
                break   # only first match per position

    return candidates


# ---------------------------------------------------------
# Date candidates
# ---------------------------------------------------------

def _date_candidates(source_token: str) -> list:
    """
    Generate plausible date interpretations.

    If both day and month are <= 12, the ordering is ambiguous; add the
    day/month swap. Otherwise, the as-is date is the only candidate.
    """
    token = source_token.strip()
    candidates = [{"value": token, "reason": "as_is", "weight": 1.0}]

    sep = None
    for s in ("/", "-"):
        if s in token:
            sep = s
            break
    if sep is None:
        return candidates

    parts = token.split(sep)
    if len(parts) != 3:
        return candidates

    try:
        a, b, c = (int(p) for p in parts)
    except ValueError:
        return candidates

    # Swap only if both a and b can be a day and a month
    if a <= 12 and b <= 12:
        swapped = f"{b:02d}{sep}{a:02d}{sep}{c:04d}" if c > 99 else f"{b:02d}{sep}{a:02d}{sep}{c:02d}"
        if swapped != token:
            candidates.append({
                "value": swapped,
                "reason": "swap_day_month",
                "weight": 0.6,
            })

    return candidates


# ---------------------------------------------------------
# Text candidates (company, address)
# ---------------------------------------------------------

def _text_candidates(source_token: str) -> list:
    """
    For text fields, only return the as-is interpretation in this version.
    These fields do not enter the decision function, so generating
    character-level alternatives adds noise without changing decisions.
    Extend this if the decision rule is widened.
    """
    return [{"value": source_token, "reason": "as_is", "weight": 1.0}]


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def generate_candidates(field_name: str, source_token: str) -> list:
    """
    Return a list of candidate interpretations for one uncertain field.

    The first candidate is always the as-is interpretation (weight 1.0).
    Subsequent candidates are the constrained alternatives.
    """
    if not source_token:
        return []

    if field_name == "total":
        return _money_candidates(source_token)

    if field_name == "date":
        return _date_candidates(source_token)

    if field_name in ("company", "address"):
        return _text_candidates(source_token)

    return [{"value": source_token, "reason": "as_is", "weight": 1.0}]


# ---------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("total", "9,00"),
        ("total", "9.00"),
        ("total", "1,234.56"),
        ("total", "1.500"),
        ("date",  "25/12/2018"),
        ("date",  "05/06/2018"),
        ("date",  "12/12/2018"),
        ("company", "BOOK TA -K (TAMAN DAYA) SDN BHD"),
    ]

    for field, token in tests:
        print(f"\n{field}: {token!r}")
        for c in generate_candidates(field, token):
            print(f"    -> {c['value']!r:30s}  reason={c['reason']:25s} w={c['weight']}")