"""
uncertainty.py

Step 5 — Semantic uncertainty detection.

Given the (fields, lines, provenance) triple from field_extractor, decide
which extracted fields are UNCERTAIN, and attach a reason + a numeric
uncertainty score in [0, 1].

Sources of uncertainty used here:
    1. Low OCR confidence on the source tokens.
    2. Ambiguous money format (e.g. "9,00" could be 9.00 or 900).
    3. Ambiguous date format (dd/mm vs mm/dd cannot be decided).
    4. Missing field (extractor returned None).

The output is a dict:

    {
        "total":   {"reason": "low_confidence", "score": 0.45, "details": {...}},
        "date":    {"reason": "ambiguous_format", "score": 0.30, "details": {...}},
        ...
    }

Only fields that are actually uncertain appear. Fields that are confidently
extracted and unambiguous are simply absent.

This module is deliberately conservative: it flags uncertainty when there
is evidence for it, and stays silent otherwise. Over-flagging creates
noise; under-flagging hides real decision risk. The thresholds below are
chosen to be slightly permissive so that the downstream modules can
prune with decision impact.
"""

from typing import Optional


# ---------------------------------------------------------
# Thresholds (single place; tune in one spot)
# ---------------------------------------------------------

LOW_CONFIDENCE_THRESHOLD = 70.0     # OCR confidence below this -> uncertain
MEDIUM_CONFIDENCE_THRESHOLD = 85.0  # below this -> mildly uncertain


# ---------------------------------------------------------
# 1. Field-level checks
# ---------------------------------------------------------

def _uncertainty_from_confidence(prov: dict) -> Optional[dict]:
    """
    Score uncertainty from source-token OCR confidence.

    Returns a dict {reason, score, details} or None if the field is
    confidently extracted.
    """
    conf = prov.get("confidence")
    if conf is None:
        return None

    if conf < LOW_CONFIDENCE_THRESHOLD:
        # Map [0, LOW] -> [1.0, 0.5]
        score = 1.0 - (conf / LOW_CONFIDENCE_THRESHOLD) * 0.5
        return {
            "reason": "low_confidence",
            "score": round(min(max(score, 0.5), 1.0), 3),
            "details": {"confidence": conf},
        }

    if conf < MEDIUM_CONFIDENCE_THRESHOLD:
        # Map [LOW, MEDIUM] -> [0.5, 0.15]
        span = MEDIUM_CONFIDENCE_THRESHOLD - LOW_CONFIDENCE_THRESHOLD
        score = 0.5 - ((conf - LOW_CONFIDENCE_THRESHOLD) / span) * 0.35
        return {
            "reason": "medium_confidence",
            "score": round(score, 3),
            "details": {"confidence": conf},
        }

    return None


def _uncertainty_from_money_format(source_token: str) -> Optional[dict]:
    """
    Flag money tokens whose separator is ambiguous.

    Examples:
        "9,00"     -> ambiguous (decimal comma vs thousands)
        "1.234,56" -> ambiguous (European format)
        "9.00"     -> unambiguous
        "1,234.56" -> unambiguous
    """
    if not source_token:
        return None

    has_comma = "," in source_token
    has_dot   = "." in source_token

    if not has_comma:
        return None

    if has_comma and not has_dot:
        # "9,00" style: only a comma. Could be decimal or thousands.
        return {
            "reason": "ambiguous_money_separator",
            "score": 0.30,
            "details": {"source_token": source_token},
        }

    # Both separators present -> last one is decimal, unambiguous.
    return None


def _uncertainty_from_date_format(source_token: str) -> Optional[dict]:
    """
    Flag dates whose day/month ordering is ambiguous.

    A date like "25/12/2018" is unambiguous (25 cannot be a month).
    A date like "05/06/2018" is ambiguous.
    """
    if not source_token:
        return None

    parts = None
    for sep in ("/", "-"):
        if sep in source_token:
            parts = source_token.split(sep)
            break

    if not parts or len(parts) != 3:
        return None

    try:
        a, b, _ = (int(p) for p in parts)
    except ValueError:
        return None

    # If either leading number is > 12, ordering is forced.
    if a > 12 or b > 12:
        return None

    # Both <= 12 -> ambiguous dd/mm vs mm/dd
    return {
        "reason": "ambiguous_date_order",
        "score": 0.25,
        "details": {"source_token": source_token},
    }


# ---------------------------------------------------------
# 2. Combine checks per field
# ---------------------------------------------------------

def _field_uncertainty(field_name: str, prov: Optional[dict]) -> Optional[dict]:
    """
    Combine confidence-based and format-based evidence for one field.
    """
    if prov is None:
        return {
            "reason": "missing",
            "score": 1.0,
            "details": {},
        }

    candidates = []

    conf_unc = _uncertainty_from_confidence(prov)
    if conf_unc:
        candidates.append(conf_unc)

    source_token = prov.get("source_token", "")

    if field_name == "total":
        fmt_unc = _uncertainty_from_money_format(source_token)
        if fmt_unc:
            candidates.append(fmt_unc)

    if field_name == "date":
        fmt_unc = _uncertainty_from_date_format(source_token)
        if fmt_unc:
            candidates.append(fmt_unc)

    if not candidates:
        return None

    # Pick the strongest signal, but remember all reasons.
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[0]

    return {
        "reason": top["reason"],
        "score": top["score"],
        "details": {
            "all_reasons": [c["reason"] for c in candidates],
            "source_token": source_token,
        },
    }


# ---------------------------------------------------------
# 3. Public API
# ---------------------------------------------------------

def detect_uncertainty(fields: dict, provenance: dict) -> dict:
    """
    Return {field_name: {reason, score, details}} for uncertain fields only.
    """
    uncertain = {}

    for field_name in ("company", "date", "address", "total"):
        result = _field_uncertainty(field_name, provenance.get(field_name))
        if result is not None:
            uncertain[field_name] = result

    return uncertain


# ---------------------------------------------------------
# 4. CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    import json
    from pathlib import Path
    from src.field_extractor import load_ocr_result, extract_fields

    files = sorted(Path("ocr_results/train").glob("*.json"))[:20]

    for f in files:
        r = load_ocr_result(f)
        fields, _, provenance = extract_fields(r)
        uncertain = detect_uncertainty(fields, provenance)

        print(f"\n{f.name}")
        print(f"  fields    : {fields}")
        print(f"  uncertain : {list(uncertain.keys())}")
        for name, info in uncertain.items():
            print(f"    {name:8s} reason={info['reason']:25s} score={info['score']}")