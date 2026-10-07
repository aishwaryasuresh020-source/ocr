"""One-command demo. Run: python run_demo.py"""
import subprocess
import sys
import argparse

from src.decision import load_policy

def run(cmd):
    print("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)

parser = argparse.ArgumentParser(description="Run the OCR decision system demo")
parser.add_argument("--policy", help="Policy JSON path")
parser.add_argument("--threshold", type=float, help="Deployment threshold override")
args = parser.parse_args()
try:
    load_policy(args.policy, args.threshold)
except (OSError, ValueError) as exc:
    raise SystemExit(str(exc))

policy_args = []
if args.policy:
    policy_args.extend(["--policy", args.policy])
if args.threshold is not None:
    policy_args.extend(["--threshold", str(args.threshold)])

print("=" * 60)
print("OCR DECISION SYSTEM - DEMO")
print("=" * 60)

run([sys.executable, "-m", "src.min_verification", *policy_args])
run([sys.executable, "-m", "src.adaptive", *policy_args])
run([sys.executable, "-m", "src.evaluate", *policy_args])

print("\nDone.")
