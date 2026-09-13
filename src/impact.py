"""
impact.py

Step 8 — Counterfactual Decision Impact Score.

For every uncertain field, substitute each candidate interpretation into
the field set, run the decision function, and measure how much the
downstream decision varies.

Decision-aware by construction:
    - If the field has no path to any decision condition (per the
      dependency graph), impact = 0 regardless of how uncertain it is.
    - If the field is decision-relevant but all candidates lead to the
      same decision, impact = 0.
    - If candidates lead to different decisions, impact > 0, computed as
      a normalized weighted entropy over the decision distribution.
    - Missing fields that are decision-relevant get impact = 1.0.

This is the module that turns "uncertainty" into "decision risk".

Public API
----------
decision_impact_scores(fields, uncertain, provenance, graph) -> dict
"""

import math

from src.candidates import generate_candidates
from src.decision import decision_function
from src.dependency_graph import fields_influencing_decision


# Number of distinct decision labels in the current rule:
# AUTO_APPROVE, MANAGER_REVIEW, REVIEW
NUM_DECISION_LABELS = 3


# ---------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------

def _weighted_entropy(outcomes):
    """
    Weighted entropy (in nats) of the decision distribution induced
    by the candidates. 0.0 if all candidates produce the same decision.
    """
    total_w = sum(o["weight"] for o in outcomes)
    if total_w <= 0:
        return 0.0

    probs = {}
    for o in outcomes:
        probs[o["decision"]] = probs.get(o["decision"], 0.0) + (o["weight"] / total_w)

    if len(probs) <= 1:
        return 0.0

    return -sum(p * math.log(p + 1e-12) for p in probs.values())


def _normalize_entropy(entropy):
    """Normalize to [0, 1] by dividing by log(NUM_DECISION_LABELS)."""
    denom = math.log(NUM_DECISION_LABELS)
    return min(entropy / denom, 1.0)


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def decision_impact_scores(fields, uncertain, provenance, graph):
    """
    Return {field_name: impact_info} for every uncertain field.

    impact_info:
        {
            "impact":                 float in [0, 1],
            "base_decision":          decision on unmodified fields,
            "num_distinct_decisions": int,
            "outcomes":               [{candidate, decision, weight, reason}, ...],
            "decision_relevant":      bool,
            "note":                   optional str
        }
    """
    relevant = fields_influencing_decision(graph)
    base_decision = decision_function(fields)

    scores = {}

    for field_name, unc_info in uncertain.items():
        is_relevant = field_name in relevant
        prov = provenance.get(field_name)

        # --- Missing field ------------------------------------------------
        if prov is None:
            scores[field_name] = {
                "impact": 1.0 if is_relevant else 0.0,
                "base_decision": base_decision,
                "num_distinct_decisions": 1,
                "outcomes": [],
                "decision_relevant": is_relevant,
                "note": "field_missing",
            }
            continue

        # --- Field not decision-relevant ---------------------------------
        if not is_relevant:
            scores[field_name] = {
                "impact": 0.0,
                "base_decision": base_decision,
                "num_distinct_decisions": 1,
                "outcomes": [],
                "decision_relevant": False,
            }
            continue

        # --- Generate candidates and evaluate through the decision ------
        source_token = prov.get("source_token", "")
        candidates = generate_candidates(field_name, source_token)

        if not candidates:
            scores[field_name] = {
                "impact": 0.0,
                "base_decision": base_decision,
                "num_distinct_decisions": 1,
                "outcomes": [],
                "decision_relevant": True,
                "note": "no_candidates",
            }
            continue

        outcomes = []
        for c in candidates:
            modified = dict(fields)
            modified[field_name] = c["value"]
            outcomes.append({
                "candidate": c["value"],
                "decision":  decision_function(modified),
                "weight":    c["weight"],
                "reason":    c["reason"],
            })

        distinct = {o["decision"] for o in outcomes}
        entropy = _weighted_entropy(outcomes)
        impact = _normalize_entropy(entropy)

        scores[field_name] = {
            "impact": round(impact, 3),
            "base_decision": base_decision,
            "num_distinct_decisions": len(distinct),
            "outcomes": outcomes,
            "decision_relevant": True,
        }

    return scores


# ---------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from src.field_extractor import load_ocr_result, extract_fields
    from src.uncertainty import detect_uncertainty
    from src.dependency_graph import build_graph

    graph = build_graph()
    files = sorted(Path("ocr_results/train").glob("*.json"))[:8]

    for f in files:
        r = load_ocr_result(f)
        fields, _, prov = extract_fields(r)
        uncertain = detect_uncertainty(fields, prov)
        impacts = decision_impact_scores(fields, uncertain, prov, graph)

        print("\n" + "=" * 65)
        print(f"{f.name}")
        print(f"  total     : {fields['total']}")
        print(f"  decision  : {decision_function(fields)}")
        print(f"  uncertain : {list(uncertain.keys())}")
        print("  impacts   :")
        for fname, info in impacts.items():
            print(
                f"    {fname:8s} impact={info['impact']:.3f} "
                f"distinct={info['num_distinct_decisions']} "
                f"relevant={info['decision_relevant']}"
                + (f" note={info.get('note')}" if info.get("note") else "")
            )
            for o in info["outcomes"]:
                c = str(o["candidate"])[:22]
                print(f"        {c:24s} -> {o['decision']:15s} w={o['weight']}")