"""Policy-driven downstream decision function and verification costs."""

from pathlib import Path
import json
import math


POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "policy.json"

VERIFICATION_COST = {
    "company": 1,
    "date": 1,
    "address": 3,
    "total": 2,
}


def default_policy():
    """Return the deployment policy template; deployments supply a threshold."""
    return {
        "name": "default",
        "threshold": None,
        "currency": "INR",
        "labels": {
            "above": "MANAGER_REVIEW",
            "below": "AUTO_APPROVE",
            "missing": "REVIEW",
        },
    }


def load_policy(policy_path=None, threshold=None, require_threshold=True):
    """Load a policy JSON file and optionally override its threshold."""
    path = Path(policy_path) if policy_path else POLICY_PATH
    if policy_path and not path.exists():
        raise FileNotFoundError(f"policy file not found: {path}")
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            policy = json.load(handle)
    else:
        policy = default_policy()

    if threshold is not None:
        policy["threshold"] = threshold
    if require_threshold:
        validate_policy(policy, require_threshold=True)
    return policy


def validate_policy(policy, require_threshold=True):
    """Validate policy fields and optionally require a usable threshold."""
    if not isinstance(policy, dict):
        raise ValueError("policy is required; supply a threshold before running")

    labels = policy.get("labels")
    if not isinstance(labels, dict) or any(
        not isinstance(labels.get(key), str) or not labels[key]
        for key in ("above", "below", "missing")
    ):
        raise ValueError("policy labels must define above, below, and missing")
    if not isinstance(policy.get("currency"), str) or not policy["currency"].strip():
        raise ValueError("policy currency is required")

    value = policy.get("threshold")
    if value is None:
        if require_threshold:
            raise ValueError("policy is required; supply a threshold before running")
        return policy
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("policy threshold must be numeric") from None
    if not math.isfinite(number):
        raise ValueError("policy threshold must be a finite number")
    return policy


def decision_function(fields, policy=None):
    """Apply the explicit policy to the extracted total."""
    validate_policy(policy, require_threshold=True)
    total = fields.get("total")
    if total is None:
        return policy["labels"]["missing"]
    try:
        total = float(total)
    except (TypeError, ValueError):
        return policy["labels"]["missing"]
    if total > float(policy["threshold"]):
        return policy["labels"]["above"]
    return policy["labels"]["below"]


def decision_conditions(policy):
    """Named predicates used by the dependency graph for this policy."""
    validate_policy(policy, require_threshold=False)

    def total_le_threshold(fields):
        validate_policy(policy, require_threshold=True)
        try:
            return fields.get("total") is not None and float(fields["total"]) <= float(policy["threshold"])
        except (TypeError, ValueError):
            return False

    return {
        "total_present": lambda fields: fields.get("total") is not None,
        "total_le_threshold": total_le_threshold,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect policy-driven decisions")
    parser.add_argument("--policy", help="Policy JSON path")
    parser.add_argument("--threshold", type=float, help="Deployment threshold override")
    args = parser.parse_args()
    active_policy = load_policy(args.policy, args.threshold)
    for sample in ({"total": 9.0}, {"total": 10.0}, {"total": 48.0}, {"total": None}):
        print(sample, "->", decision_function(sample, active_policy))
