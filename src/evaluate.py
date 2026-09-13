"""
evaluate.py

Step 11 — End-to-end evaluation.

Runs the pipeline across all invoices in a split and compares five
strategies on three metrics:

    Strategies:
        verify_nothing       -- trust raw OCR fields
        verify_all_fields    -- verify every field (upper bound)
        verify_all_uncertain -- verify every field flagged as uncertain
        verify_by_confidence -- verify fields whose OCR confidence < threshold
        adaptive_ours        -- the invention

    Metrics:
        decision accuracy vs ground truth decision
        average verifications per invoice
        average cost per invoice

Ground truth stands in for human/system verification in this prototype.
"""

from pathlib import Path
from collections import defaultdict

from src.field_extractor import load_ocr_result, extract_fields
from src.uncertainty import detect_uncertainty
from src.decision import decision_function, VERIFICATION_COST
from src.dependency_graph import build_graph
from src.min_verification import load_ground_truth
from src.adaptive import adaptive_verify


ALL_FIELDS = ("company", "date", "address", "total")
CONFIDENCE_THRESHOLD = 70.0


# ---------------------------------------------------------
# Per-invoice evaluation
# ---------------------------------------------------------

def evaluate_one(sample_id, split, graph):
    """
    Return a dict with ground-truth decision and per-method results,
    or None if OCR output or ground truth is missing.
    """
    ocr_path = Path(f"ocr_results/{split}/{sample_id}.json")
    if not ocr_path.exists():
        return None

    r = load_ocr_result(ocr_path)
    fields, _, prov = extract_fields(r)
    uncertain = detect_uncertainty(fields, prov)
    gt = load_ground_truth(sample_id, split)

    if gt is None:
        return None

    gt_decision = decision_function(gt)
    results = {}

    # --- Baseline 1: verify nothing ---
    results["verify_nothing"] = {
        "final_decision": decision_function(fields),
        "verifications": 0,
        "cost": 0,
    }

    # --- Baseline 2: verify all fields ---
    verified = dict(fields)
    for f in ALL_FIELDS:
        if gt.get(f) is not None:
            verified[f] = gt[f]
    results["verify_all_fields"] = {
        "final_decision": decision_function(verified),
        "verifications": len(ALL_FIELDS),
        "cost": sum(VERIFICATION_COST.get(f, 1) for f in ALL_FIELDS),
    }

    # --- Baseline 3: verify all uncertain ---
    verified = dict(fields)
    n, cost = 0, 0
    for f in uncertain:
        if gt.get(f) is not None:
            verified[f] = gt[f]
        n += 1
        cost += VERIFICATION_COST.get(f, 1)
    results["verify_all_uncertain"] = {
        "final_decision": decision_function(verified),
        "verifications": n,
        "cost": cost,
    }

    # --- Baseline 4: verify by OCR confidence ---
    verified = dict(fields)
    n, cost = 0, 0
    for f in ALL_FIELDS:
        entry = prov.get(f)
        if entry is None:
            continue
        if entry.get("confidence", 100.0) < CONFIDENCE_THRESHOLD:
            if gt.get(f) is not None:
                verified[f] = gt[f]
            n += 1
            cost += VERIFICATION_COST.get(f, 1)
    results["verify_by_confidence"] = {
        "final_decision": decision_function(verified),
        "verifications": n,
        "cost": cost,
    }

    # --- Method: adaptive (ours) ---
    _, _, info = adaptive_verify(fields, uncertain, prov, gt, graph)
    results["adaptive_ours"] = {
        "final_decision": info["final_decision"],
        "verifications": info["steps"],
        "cost": info["total_cost"],
    }

    return {
        "id": sample_id,
        "gt_decision": gt_decision,
        "results": results,
    }


# ---------------------------------------------------------
# Aggregate over a split
# ---------------------------------------------------------

def evaluate_split(split, graph):
    ocr_dir = Path(f"ocr_results/{split}")
    if not ocr_dir.exists():
        print(f"[skip] no OCR output for split: {split}")
        return None

    ids = sorted(p.stem for p in ocr_dir.glob("*.json"))

    methods = [
        "verify_nothing",
        "verify_all_fields",
        "verify_all_uncertain",
        "verify_by_confidence",
        "adaptive_ours",
    ]

    totals = {
        m: {"correct": 0, "verifications": 0, "cost": 0} for m in methods
    }
    n_evaluated = 0
    skipped = 0

    for sample_id in ids:
        row = evaluate_one(sample_id, split, graph)
        if row is None:
            skipped += 1
            continue

        n_evaluated += 1
        gt_dec = row["gt_decision"]

        for m in methods:
            r = row["results"][m]
            if r["final_decision"] == gt_dec:
                totals[m]["correct"] += 1
            totals[m]["verifications"] += r["verifications"]
            totals[m]["cost"] += r["cost"]

    if n_evaluated == 0:
        print(f"[skip] no evaluable invoices in split: {split}")
        return None

    table = {}
    for m in methods:
        t = totals[m]
        table[m] = {
            "accuracy":      t["correct"] / n_evaluated,
            "avg_verif":     t["verifications"] / n_evaluated,
            "avg_cost":      t["cost"] / n_evaluated,
        }

    return {
        "split": split,
        "n_evaluated": n_evaluated,
        "n_skipped": skipped,
        "table": table,
    }


# ---------------------------------------------------------
# Pretty print
# ---------------------------------------------------------

def print_table(result):
    if result is None:
        return

    print()
    print("=" * 78)
    print(f"EVALUATION — {result['split'].upper()}")
    print(f"evaluated: {result['n_evaluated']}   skipped: {result['n_skipped']}")
    print("=" * 78)
    header = f"{'method':22s} {'accuracy':>10s} {'avg verif':>12s} {'avg cost':>12s}"
    print(header)
    print("-" * 78)

    order = [
        "verify_nothing",
        "verify_by_confidence",
        "verify_all_uncertain",
        "verify_all_fields",
        "adaptive_ours",
    ]
    for m in order:
        t = result["table"][m]
        print(
            f"{m:22s} "
            f"{100*t['accuracy']:>9.1f}% "
            f"{t['avg_verif']:>12.3f} "
            f"{t['avg_cost']:>12.3f}"
        )
    print("=" * 78)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":
    graph = build_graph()
    for split in ("train", "test"):
        result = evaluate_split(split, graph)
        print_table(result)