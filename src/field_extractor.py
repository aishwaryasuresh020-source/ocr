"""
field_extractor.py

Step 3 — Semantic field extraction with provenance.

Takes OCR JSON (produced by ocr_engine.py) and extracts the four
SROIE-relevant semantic fields: company, date, address, total.

Returns THREE things from extract_fields():

    fields      -- {field_name: value}          flat dict (same as before)
    lines       -- reconstructed OCR lines
    provenance  -- {field_name: {...}}          rich metadata per field

The provenance dict is what downstream modules (uncertainty detection,
candidate generation, decision impact scoring) need in order to know
which OCR content produced each field, and how reliable it is.

Design notes:
- Deterministic: same input JSON => same output, always.
- `total` value is a float.
- Address excludes the line already chosen as company.
- Field confidence = minimum confidence among valid source words
  (Tesseract uses -1 for non-text tokens; those are ignored).
"""

import json
import re
from pathlib import Path


# ---------------------------------------------------------
# 0. I/O
# ---------------------------------------------------------

def load_ocr_result(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------
# 1. RECONSTRUCT OCR LINES
# ---------------------------------------------------------

def reconstruct_lines(words):
    """
    Group word-level OCR tokens into lines using (block, par, line),
    sorted by block/par/line, and each line's words sorted left-to-right.
    """
    groups = {}

    for w in words:
        key = (w["block_num"], w["par_num"], w["line_num"])
        groups.setdefault(key, []).append(w)

    lines = []
    for key in sorted(groups.keys()):
        line_words = sorted(groups[key], key=lambda w: w["bbox"]["x"])
        text = " ".join(w["text"] for w in line_words).strip()
        if text:
            lines.append({
                "text": text,
                "words": line_words,
            })

    return lines


def _min_confidence(word_objs):
    """Minimum valid confidence among words. Returns 0.0 if none valid."""
    valid = [w["confidence"] for w in word_objs if w["confidence"] >= 0]
    return float(min(valid)) if valid else 0.0


# ---------------------------------------------------------
# 2. COMPANY EXTRACTION
# ---------------------------------------------------------

COMPANY_TERMS = [
    "sdn bhd", "sdn. bhd", "ltd", "limited", "llc", "inc",
    "corp", "corporation", "enterprise", "company", "co.",
    "store", "mart", "shop", "supermarket", "trading",
    "restaurant", "hotel", "pharmacy",
]

PERSONAL_TERMS = [
    "cashier", "member", "customer", "document",
    "date", "phone", "tel", "mobile",
]

ADDRESS_TERMS_FOR_COMPANY = [
    "jalan", "street", "road", "taman", "postcode",
    "selangor", "johor bahru", "kuala", "lorong",
]


def _company_score(text, line_index):
    score = 0
    lower = text.lower()

    for term in COMPANY_TERMS:
        if term in lower:
            score += 10

    if line_index < 8:
        score += 3

    for term in PERSONAL_TERMS:
        if term in lower:
            score -= 10

    for term in ADDRESS_TERMS_FOR_COMPANY:
        if term in lower:
            score -= 3

    if len(text) < 4:
        score -= 5

    return score


def extract_company_with_provenance(lines):
    candidates = []

    for index, line in enumerate(lines[:12]):
        text = line["text"].strip()
        if not text:
            continue
        candidates.append({
            "index": index,
            "text": text,
            "words": line["words"],
            "score": _company_score(text, index),
        })

    if not candidates:
        return None

    # Highest score wins; ties broken by earliest line.
    candidates.sort(key=lambda c: (-c["score"], c["index"]))
    best = candidates[0]

    if best["score"] < 3:
        return None

    return {
        "value": best["text"],
        "source_text": best["text"],
        "source_token": best["text"],
        "line_index": best["index"],
        "words": best["words"],
        "confidence": _min_confidence(best["words"]),
    }


# ---------------------------------------------------------
# 3. DATE EXTRACTION
# ---------------------------------------------------------

DATE_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{2,4}[/-]\d{1,2}[/-]\d{1,2}\b",
]


def extract_date_with_provenance(lines):
    preferred = [ln for ln in lines if re.search(r"(?i)\bdate\b", ln["text"])]
    search_order = preferred + lines

    for line in search_order:
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line["text"])
            if not match:
                continue

            # Find index by identity, not equality
            line_index = next(
                i for i, ln in enumerate(lines) if ln is line
            )

            return {
                "value": match.group(0),
                "source_text": line["text"],
                "source_token": match.group(0),
                "line_index": line_index,
                "words": line["words"],
                "confidence": _min_confidence(line["words"]),
            }

    return None


# ---------------------------------------------------------
# 4. ADDRESS EXTRACTION
# ---------------------------------------------------------

ADDRESS_TERMS = [
    "jalan", "street", "road", "taman", "lorong", "lot",
    "no.", "postcode",
    "selangor", "johor", "kuala", "penang", "perak",
    "kedah", "melaka", "pahang", "terengganu", "kelantan",
    "negeri", "sarawak", "sabah",
]


def _is_address_line(text):
    lower = text.lower()
    return any(term in lower for term in ADDRESS_TERMS)


def extract_address_with_provenance(lines, company_text=None):
    collected = []

    for index, line in enumerate(lines[:15]):
        text = line["text"].strip()
        if not text:
            continue

        # Skip the company line
        if company_text and text == company_text:
            continue

        if _is_address_line(text):
            collected.append({
                "index": index,
                "text": text,
                "words": line["words"],
            })

    if not collected:
        return None

    # Keep only contiguous / near-contiguous lines (gap <= 2).
    selected_texts = []
    selected_words = []
    previous_index = None

    for entry in collected:
        if previous_index is None or entry["index"] - previous_index <= 2:
            selected_texts.append(entry["text"])
            selected_words.extend(entry["words"])
        previous_index = entry["index"]

    if not selected_texts:
        return None

    joined = " ".join(selected_texts)

    return {
        "value": joined,
        "source_text": joined,
        "source_token": joined,
        "line_index": collected[0]["index"],
        "words": selected_words,
        "confidence": _min_confidence(selected_words),
    }


# ---------------------------------------------------------
# 5. MONEY EXTRACTION AND NORMALIZATION
# ---------------------------------------------------------

MONEY_PATTERN = r"\b\d+(?:[,.]\d{2})\b"


def extract_money_values(text):
    return re.findall(MONEY_PATTERN, text)


def normalize_money(value):
    """
    "9.00"      -> 9.0
    "9,00"      -> 9.0
    "1,234.56"  -> 1234.56
    "1.234,56"  -> 1234.56
    """
    value = value.strip()

    if "." in value and "," in value:
        if value.rfind(".") > value.rfind(","):
            value = value.replace(",", "")
        else:
            value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        parts = value.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")

    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------------------------------
# 6. TOTAL EXTRACTION
# ---------------------------------------------------------

def extract_total_with_provenance(lines):
    candidates = []

    for index, line in enumerate(lines):
        text = line["text"].strip()

        if not re.search(r"(?i)\btotal\b", text):
            continue

        for value in extract_money_values(text):
            numeric = normalize_money(value)
            if numeric is None:
                continue
            candidates.append({
                "raw_value": value,
                "numeric": numeric,
                "line_index": index,
                "text": text,
                "words": line["words"],
            })

    if not candidates:
        return None

    # Prefer non-rounding-adjustment lines
    preferred = [
        c for c in candidates
        if "rounding adjustment" not in c["text"].lower()
        and "round." not in c["text"].lower()
    ]
    if preferred:
        candidates = preferred

    best = candidates[-1]

    return {
        "value": best["numeric"],
        "source_text": best["text"],
        "source_token": best["raw_value"],     # e.g. "9,00"
        "line_index": best["line_index"],
        "words": best["words"],
        "confidence": _min_confidence(best["words"]),
    }


# ---------------------------------------------------------
# 7. COMPLETE FIELD EXTRACTION
# ---------------------------------------------------------

def extract_fields(ocr_result):
    """
    Returns (fields, lines, provenance).

    fields      -- flat dict, for decision_function
    lines       -- reconstructed OCR lines
    provenance  -- rich per-field metadata
    """
    words = ocr_result["words"]
    lines = reconstruct_lines(words)

    company_prov = extract_company_with_provenance(lines)
    company_text = company_prov["value"] if company_prov else None

    date_prov    = extract_date_with_provenance(lines)
    address_prov = extract_address_with_provenance(lines, company_text=company_text)
    total_prov   = extract_total_with_provenance(lines)

    provenance = {
        "company": company_prov,
        "date":    date_prov,
        "address": address_prov,
        "total":   total_prov,
    }

    fields = {
        "company": company_prov["value"] if company_prov else None,
        "date":    date_prov["value"]    if date_prov    else None,
        "address": address_prov["value"] if address_prov else None,
        "total":   total_prov["value"]   if total_prov   else None,
    }

    return fields, lines, provenance


# ---------------------------------------------------------
# 8. CLI TEST
# ---------------------------------------------------------

if __name__ == "__main__":

    sample_file = Path("ocr_results/train/X00016469612.json")

    if not sample_file.exists():
        raise SystemExit(f"Sample OCR file not found: {sample_file}")

    result = load_ocr_result(sample_file)
    fields, lines, provenance = extract_fields(result)

    print("\n===== RECONSTRUCTED OCR LINES =====\n")
    for i, line in enumerate(lines, start=1):
        print(f"{i}: {line['text']}")

    print("\n===== EXTRACTED SEMANTIC FIELDS =====\n")
    for name, value in fields.items():
        print(f"{name.upper()}: {value!r}")

    print("\n===== PROVENANCE =====\n")
    for name, prov in provenance.items():
        if prov is None:
            print(f"{name.upper()}: (not found)\n")
            continue
        print(f"{name.upper()}:")
        print(f"    value        = {prov['value']!r}")
        print(f"    source_token = {prov['source_token']!r}")
        print(f"    source_text  = {prov['source_text']!r}")
        print(f"    line_index   = {prov['line_index']}")
        print(f"    confidence   = {prov['confidence']}")
        print(f"    num_words    = {len(prov['words'])}")
        print()