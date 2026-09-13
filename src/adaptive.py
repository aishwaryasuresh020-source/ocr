"""
adaptive.py

Step 10 — Impact-driven adaptive sequential verification.

Same decision-invariance objective as min_verification.py, but executed
as a SEQUENTIAL process:

    while not invariant(verified, remaining):
        pick the highest-impact / lowest-cost unverified field
        verify it (substitute ground truth)
        remove it from remaining
    stop

The output is a TRACE of verification actions, which is exactly what
a human reviewer would see. The trace is also what proves the
"stop once the decision becomes invariant" property of the invention.

Public API:
    adaptive_verify(fields, uncertain, provenance, ground_truth, graph)
        -> (verified_fields, trace, info)
"""

from src.candidates import generate_candidates
from src.decision import decision_function, VERIFICATION_COST
from src.dependency_graph import fields_influencing_decision
from src.impact import decision_impact_scores
from src.min_verification import (
    _candidate_values,
    decision_invariant,
    load_ground_truth,
)


# ---------------------------------------------------------
# Select next field to verify
# ---------------------------------------------------------

def _select_next(fields, remaining, provenance, graph):
    """
    Pick the next field to verify.

    Ranking rule:
        1. Higher decision impact first.
        2. Lower verification cost first (tie-break).
        3. Field name (final tie-break, for determinism).
    """
    sub_uncertain = {f: {"reason": "remaining"} for f in remaining}

    impacts = decision_impact_scores(
        fields, sub_uncertain, provenance, graph
    )

    def sort_key(f):
        impact = impacts.get(f, {}).get("impact", 0.0)
        cost = VERIFICATION_COST.get(f, 1)
        return (-impact, cost, f)

    ordered = sorted(remaining, key=sort_key)
    return ordered[0]


# ---------------------------------------------------------
# Adaptive loop
# ---------------------------------------------------------

def adaptive_verify(fields, uncertain, provenance, ground_truth, graph):
    """
    Sequentially verify fields until the decision is invariant.

    Returns:
        verified_fields -- the field dict after all verification actions
        trace           -- [{step, field, impact, cost,
                            decision_after, invariant_after}, ...]
        info            -- summary dict with 'steps' == number of
                           verification actions actually performed
    """
    candidates_map = {
        f: _candidate_values(f, provenance, fields, graph)
        for f in uncertain
    }

    verified = dict(fields)
    remaining = set(uncertain.keys())
    trace = []
    total_cost = 0
    step = 0

    max_steps = len(remaining) + 1  # hard cap; prevents infinite loops

    while remaining and step < max_steps:

        # Check invariance BEFORE selecting anything.
        # If already invariant, stop — no verification needed.
        if decision_invariant(
            verified, remaining, candidates_map, decision_function
        ):
            break

        # Select the next field and count this as a real step.
        step += 1
        field = _select_next(verified, remaining, provenance, graph)

        # Compute current impact for the trace.
        sub_uncertain = {field: {"reason": "selected"}}
        impact_info = decision_impact_scores(
            verified, sub_uncertain, provenance, graph
        ).get(field, {})
        impact = impact_info.get("impact", 0.0)

        # Apply ground-truth value if available.
        if ground_truth is not None and ground_truth.get(field) is not None:
            verified[field] = ground_truth[field]

        remaining.discard(field)
        cost = VERIFICATION_COST.get(field, 1)
        total_cost += cost

        invariant_now = decision_invariant(
            verified, remaining, candidates_map, decision_function
        )

        trace.append({
            "step": step,
            "field": field,
            "impact": impact,
            "cost": cost,
            "decision_after": decision_function(verified),
            "invariant_after": invariant_now,
        })

    info = {
        "steps": step,
        "total_cost": total_cost,
        "final_decision": decision_function(verified),
        "remaining_uncertain": sorted(remaining),
        "terminated_by_invariance": decision_invariant(
            verified, remaining, candidates_map, decision_function
        ),
    }
    return verified, trace, info


# ---------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from src.field_extractor import load_ocr_result, extract_fields
    from src.uncertainty import detect_uncertainty
    from src.dependency_graph import build_graph

    graph = build_graph()
    files = sorted(Path("ocr_results/train").glob("*.json"))[:10]

    for f in files:
        r = load_ocr_result(f)
        fields, _, prov = extract_fields(r)
        uncertain = detect_uncertainty(fields, prov)
        gt = load_ground_truth(f.stem, split="train")

        verified, trace, info = adaptive_verify(
            fields, uncertain, prov, gt, graph
        )

        print("\n" + "=" * 70)
        print(f"{f.name}")
        print(f"  initial decision : {decision_function(fields)}")
        print(f"  final decision   : {info['final_decision']}")
        print(f"  total cost       : {info['total_cost']}")
        print(f"  steps            : {info['steps']}")
        print(
            f"  terminated by    : "
            f"{'invariance' if info['terminated_by_invariance'] else 'cap'}"
        )

        if trace:
            for t in trace:
                print(
                    f"    step {t['step']}: verify {t['field']:8s} "
                    f"impact={t['impact']:.3f} cost={t['cost']} "
                    f"-> {t['decision_after']} "
                    f"(invariant={t['invariant_after']})"
                )
        else:
            print("    (no verification needed)")

    print("\n" + "=" * 70)