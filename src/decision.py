"""
decision.py

Step 4 — Downstream decision function.

Maps extracted semantic fields to a discrete decision label.
Pure function of the fields dict; no I/O, no OCR, no side effects.

DECISION_THRESHOLD is chosen from the SROIE train total distribution:
    p50 = 12.6 RM
This gives roughly a 50/50 split between AUTO_APPROVE and MANAGER_REVIEW,
maximizing the number of invoices near the decision boundary — which is
the condition under which the invention is exercised.

Do not change DECISION_THRESHOLD once experiments have begun.
"""

DECISION_THRESHOLD = 12.6   # RM; median of parsed totals on SROIE train

VERIFICATION_COST = {
    "company": 1,
    "date":    1,
    "address": 3,
    "total":   2,
}


def decision_function(fields):
    """
    Rule:
        - total missing or unparseable -> "REVIEW"
        - total <= DECISION_THRESHOLD   -> "AUTO_APPROVE"
        - otherwise                     -> "MANAGER_REVIEW"
    """
    total = fields.get("total")

    if total is None:
        return "REVIEW"

    try:
        total = float(total)
    except (TypeError, ValueError):
        return "REVIEW"

    if total <= DECISION_THRESHOLD:
        return "AUTO_APPROVE"

    return "MANAGER_REVIEW"


def decision_conditions():
    """
    Named boolean conditions composing the decision.
    These are the anchors for the Decision Dependency Graph (Step 7).
    """
    return {
        "total_present": lambda f: f.get("total") is not None,
        "total_le_threshold": lambda f: (
            f.get("total") is not None
            and float(f["total"]) <= DECISION_THRESHOLD
        ),
    }


if __name__ == "__main__":
    samples = [
        {"total": 9.0},        # below threshold -> AUTO_APPROVE
        {"total": 12.6},       # exactly at threshold -> AUTO_APPROVE
        {"total": 48.0},       # above threshold -> MANAGER_REVIEW
        {"total": None},       # missing -> REVIEW
    ]
    for fields in samples:
        print(fields, "->", decision_function(fields))