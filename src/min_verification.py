"""
min_verification.py

Step 9 — Minimum-cost decision-stabilizing verification set.

Given:
    fields        -- the extracted fields (our best guess)
    uncertain     -- {field_name: {...}} from uncertainty.py
    provenance    -- from field_extractor.py
    ground_truth  -- the "oracle" verified values for this invoice
    graph         -- from dependency_graph.py
    cost_table    -- from decision.py (VERIFICATION_COST)

Compute:
    V* = argmin_{V ⊆ U}  Cost(V)
         subject to:  after replacing V with ground truth,
                      all remaining candidate interpretations of U \\ V
                      lead to the SAME downstream decision.

Returns:
    (V_star, cost, info_dict)

Key correctness details
-----------------------
1. A decision-relevant field that is MISSING gets a probe set covering
   both sides of the decision boundary. Without this, a missing total
   would trivially satisfy invariance (candidate = None) and the system
   would wrongly skip verification.

2. A decision-relevant field with LOW OCR CONFIDENCE likewise gets
   probe values added to its candidate set. This closes the accuracy
   gap against baselines that verify purely on confidence: format
   candidates alone cannot represent "OCR read the wrong number".
"""

import itertools
import json
from pathlib import Path
from typing import Optional

from src.candidates import generate_candidates
from src.decision import (
    decision_function,
    VERIFICATION_COST,
    DECISION_THRESHOLD,
)
from src.dependency_graph import fields_influencing_decision


# Threshold below which a decision-relevant field is treated as
# "possibly misread entirely" and gets decision-space probes added.
LOW_CONFIDENCE_THRESHOLD = 85.0


# ---------------------------------------------------------
# Ground truth oracle
# ---------------------------------------------------------

def load_ground_truth(sample_id: str, split: str = "train") -> Optional[dict]:
    """
    Load SROIE ground-truth fields for one invoice, normalized to the
    same shape as `fields`.
    Returns None if the processed file does not exist.
    """
    from src.field_extractor import normalize_money

    path = Path(f"processed/{split}/{sample_id}.json")
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)

    gt = record.get("ground_truth") or {}

    total_raw = gt.get("total")
    total = normalize_money(total_raw) if total_raw else None

    return {
        "company": gt.get("company"),
        "date":    gt.get("date"),
        "address": gt.get("address"),
        "total":   total,
    }


# ---------------------------------------------------------
# Candidate value space for a field
# ---------------------------------------------------------

def _candidate_values(field_name, provenance, fields, graph):
    """
    Return the list of plausible values for one uncertain field.

    - MISSING decision-relevant field: probe set spanning the boundary.
    - LOW-CONFIDENCE decision-relevant field: candidates + probes.
    - Otherwise: candidates from candidates.py (or the current value).
    """
    prov = provenance.get(field_name)
    relevant = field_name in fields_influencing_decision(graph)

    if prov is None:
        if relevant:
            return [0.0, DECISION_THRESHOLD * 10]
        return [None]

    values = [
        c["value"] for c in generate_candidates(
            field_name, prov.get("source_token", "")
        )
    ]
    if not values:
        values = [fields.get(field_name)]

    # Augment low-confidence decision-relevant fields with probes.
    # Currently only `total` is decision-relevant and numeric.
    if relevant and field_name == "total":
        conf = prov.get("confidence", 100.0)
        if conf < LOW_CONFIDENCE_THRESHOLD:
            for probe in (0.01, DECISION_THRESHOLD * 10):
                if probe not in values:
                    values.append(probe)

    return values


# ---------------------------------------------------------
# Decision invariance check
# ---------------------------------------------------------

def decision_invariant(verified_fields, remaining_uncertain,
                       candidates_map, decision_function):
    """
    True iff every combination of remaining candidate values yields the
    same decision, given verified_fields as the baseline.
    """
    remaining = list(remaining_uncertain)
    if not remaining:
        return True

    value_lists = [candidates_map[f] for f in remaining]

    decisions = set()
    for combo in itertools.product(*value_lists):
        test = dict(verified_fields)
        for f, v in zip(remaining, combo):
            test[f] = v
        decisions.add(decision_function(test))
        if len(decisions) > 1:
            return False

    return True


# ---------------------------------------------------------
# Minimum-cost verification set
# ---------------------------------------------------------

def minimum_verification_set(fields, uncertain, provenance, ground_truth,
                             graph, cost_table=None):
    """
    Enumerate all subsets of the uncertain fields, keep the ones that
    stabilize the decision, return the cheapest.

    Returns (V_star: set, cost: number, info: dict).
    """
    if cost_table is None:
        cost_table = VERIFICATION_COST

    uncertain_fields = sorted(uncertain.keys())

    candidates_map = {
        f: _candidate_values(f, provenance, fields, graph)
        for f in uncertain_fields
    }

    if not uncertain_fields:
        return set(), 0, {
            "reason": "no_uncertain_fields",
            "subset_scores": [],
        }

    subset_scores = []
    best_set = None
    best_cost = float("inf")

    for r in range(len(uncertain_fields) + 1):
        for combo in itertools.combinations(uncertain_fields, r):
            V = set(combo)

            verified = dict(fields)
            for f in V:
                if ground_truth is not None and ground_truth.get(f) is not None:
                    verified[f] = ground_truth[f]

            remaining = [f for f in uncertain_fields if f not in V]
            cost = sum(cost_table.get(f, 1) for f in V)

            if decision_invariant(verified, remaining, candidates_map,
                                  decision_function):
                subset_scores.append((tuple(sorted(V)), cost, True))
                if cost < best_cost:
                    best_cost = cost
                    best_set = V
            else:
                subset_scores.append((tuple(sorted(V)), cost, False))

    if best_set is None:
        best_set = set(uncertain_fields)
        best_cost = sum(cost_table.get(f, 1) for f in best_set)

    info = {
        "uncertain_fields": uncertain_fields,
        "subset_scores": subset_scores,
        "baseline_cost_verify_all": sum(
            cost_table.get(f, 1) for f in uncertain_fields
        ),
        "baseline_cost_verify_none": 0,
    }
    return best_set, best_cost, info


# ---------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    from src.field_extractor import load_ocr_result, extract_fields
    from src.uncertainty import detect_uncertainty
    from src.dependency_graph import build_graph

    graph = build_graph()
    files = sorted(Path("ocr_results/train").glob("*.json"))[:10]

    print("=" * 75)
    print(f"{'file':18s} {'decision':15s} {'uncertain':28s} "
          f"{'V*':18s} {'cost':>5s}")
    print("=" * 75)

    for f in files:
        r = load_ocr_result(f)
        fields, _, prov = extract_fields(r)
        uncertain = detect_uncertainty(fields, prov)
        gt = load_ground_truth(f.stem, split="train")

        V_star, cost, info = minimum_verification_set(
            fields, uncertain, prov, gt, graph
        )

        unc_str = ",".join(sorted(uncertain.keys())) or "-"
        v_str   = ",".join(sorted(V_star)) or "-"
        dec     = decision_function(fields)

        print(f"{f.stem:18s} {dec:15s} {unc_str:28s} "
              f"{v_str:18s} {cost:>5d}")

    print("=" * 75)
    print("\nNote: V* is the minimum-cost set of fields whose verification")
    print("makes the downstream decision invariant under remaining uncertainty.")