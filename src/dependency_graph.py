"""
dependency_graph.py

Step 7 — Decision Dependency Graph.

Purpose
-------
Link every semantic field to the decision conditions it can influence.
This is what makes the pipeline "decision-aware": a field whose
uncertainty cannot reach any decision condition cannot change the
decision, so its uncertainty is irrelevant.

For the current decision rule (a threshold on `total`), only `total`
participates. The other three fields have no path to the decision.

If the decision rule is later extended (e.g. `date` must be within a
review window), add entries to FIELD_TO_CONDITIONS — do not change
the rest of the pipeline.

Public API
----------
build_graph()                 -> {"fields": {...}, "conditions": {...}}
fields_influencing_decision() -> set of field names that matter
"""

from src.decision import decision_conditions


# ---------------------------------------------------------
# The graph itself
# ---------------------------------------------------------

# field_name -> list of condition names it can influence
FIELD_TO_CONDITIONS = {
    "total":   ["total_present", "total_le_threshold"],
    "company": [],
    "date":    [],
    "address": [],
}


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def build_graph():
    """
    Return the full graph structure:

        {
            "fields":     {field_name: [condition_name, ...]},
            "conditions": {condition_name: callable(fields) -> bool},
        }

    The conditions come from decision.py so that the graph and the
    decision function can never drift out of sync.
    """
    return {
        "fields":     dict(FIELD_TO_CONDITIONS),
        "conditions": decision_conditions(),
    }


def fields_influencing_decision(graph):
    """
    Return the set of field names that have a path to at least one
    decision condition.
    """
    return {name for name, conds in graph["fields"].items() if conds}


# ---------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------

if __name__ == "__main__":
    graph = build_graph()

    print("=" * 55)
    print("DECISION DEPENDENCY GRAPH")
    print("=" * 55)

    print("\nConditions (from decision.py):")
    for name in graph["conditions"]:
        print(f"    {name}")

    print("\nField -> conditions:")
    for field, conds in graph["fields"].items():
        arrow = "  -> " + ", ".join(conds) if conds else "  -> (no path)"
        print(f"    {field:10s}{arrow}")

    relevant = fields_influencing_decision(graph)
    irrelevant = set(graph["fields"]) - relevant

    print("\nDecision-relevant fields   :", sorted(relevant))
    print("Decision-irrelevant fields :", sorted(irrelevant))

    print("\nInterpretation:")
    if relevant == {"total"}:
        print("    Only `total` can change the decision.")
        print("    Uncertainty in company/date/address cannot affect the outcome")
        print("    under the current rule, so it will not trigger verification.")
    else:
        print("    Multiple fields influence the decision; check FIELD_TO_CONDITIONS.")