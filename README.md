# OCR Decision System

**Decision-Impact-Aware Detection and Minimum-Cost Decision-Stabilizing
Verification in OCR-to-Decision Pipelines.**

A computer-implemented system that detects semantic corruption in OCR
output according to its impact on a downstream decision, and computes
the minimum-cost verification set required to make that decision
invariant to remaining uncertainty.

---

## What it does

Conventional OCR verification systems decide what to verify using OCR
confidence scores. They verify fields that may be uncertain but cannot
change the downstream decision, wasting effort. This system instead:

1. Extracts semantic fields (company, date, address, total) from OCR
   output with full provenance - source token, OCR confidence, line.
2. Builds a Decision Dependency Graph linking each field to the
   conditions of a downstream decision function.
3. Detects semantic uncertainty from OCR confidence and format ambiguity.
4. Generates constrained counterfactual interpretations of uncertain
   fields using OCR confusion patterns and format rules.
5. Computes a Counterfactual Decision Impact Score by evaluating every
   interpretation through the downstream decision function.
6. Solves a constrained optimization problem to find the minimum-cost
   verification set V* such that after verification, no remaining
   interpretation can change the decision.
7. Executes verification actions and terminates automatically when the
   decision becomes invariant.

The core claim: determine the minimum verification required to make an
OCR-derived downstream decision invariant despite semantic uncertainty.

---

## Results

Evaluated on SROIE 2019 (626 train, 347 test invoices) using Tesseract.

| Method                | Train Acc | Train Cost | Test Acc | Test Cost |
|-----------------------|----------:|-----------:|---------:|----------:|
| Verify nothing        |     59.6% |      0.000 |    61.7% |     0.000 |
| Verify by confidence  |     65.5% |      3.401 |    67.1% |     3.242 |
| Verify all uncertain  |     88.3% |      5.412 |    89.9% |     5.398 |
| Verify all fields     |     91.4% |      7.000 |    92.8% |     7.000 |
| **This system**       | **88.3%** |  **2.042** |**89.9%** | **2.026** |

Identical decision accuracy to the verify-all-uncertain baseline on both
splits, at approximately 62.5% lower verification cost.

---

## Architecture

    DOCUMENT
       -> preprocessing
       -> ocr_engine          (Tesseract)
       -> field_extractor     (fields + provenance)
       -> uncertainty         (which fields might be wrong)
       -> candidates          (what they could be)
       -> dependency_graph    (which fields matter)
       -> impact              (how much they matter)
       -> min_verification    (minimum set to verify)
       -> adaptive            (sequential, stops on invariance)
       -> evaluate            (compare against baselines)

Module responsibilities:

| Module                | Purpose                                                     |
|-----------------------|-------------------------------------------------------------|
| preprocessing.py      | Parse SROIE box/entities/img triples into structured JSON   |
| ocr_engine.py         | Run Tesseract, produce word-level OCR JSON                  |
| field_extractor.py    | Extract semantic fields with provenance                     |
| decision.py           | Downstream decision function and verification cost table    |
| uncertainty.py        | Flag uncertain fields from confidence and format ambiguity  |
| candidates.py         | Generate constrained counterfactual interpretations         |
| dependency_graph.py   | Build the Decision Dependency Graph                         |
| impact.py             | Compute Counterfactual Decision Impact Scores               |
| min_verification.py   | Solve for the minimum-cost verification set V*              |
| adaptive.py           | Sequential verification with decision-invariant termination |
| evaluate.py           | Run baselines and produce the results table                 |

---

## Setup

Requires Python 3.10+ and Tesseract installed on the system.

    # macOS
    brew install tesseract

    # Ubuntu / Debian
    sudo apt install tesseract-ocr

    # Python dependencies
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

---

## Reproducing the evaluation

1. Download SROIE 2019 to a directory, e.g. ~/SROIE2019.
   It must contain train/ and test/, each with box/, entities/, img/.

2. Preprocess:

       python3 -m src.preprocessing --dataset-root ~/SROIE2019

3. Run OCR (cached; takes ~30 minutes on first run):

       python3 -m src.ocr_engine --split both --dataset-root ~/SROIE2019

4. Evaluate:

       python3 -m src.evaluate

   Expected output matches results/final_eval_v2.txt.

---

## Repository layout

    OCR_Decision_System/
    |-- src/              source modules
    |-- results/          evaluation outputs
    |-- docs/             patent specification and supporting docs
    |-- processed/        preprocessing output (gitignored)
    |-- ocr_results/      cached OCR output (gitignored)
    |-- .gitignore
    |-- README.md
    |-- requirements.txt

---

## Notes on the decision task

SROIE does not include a downstream decision label. The decision rule
used here is a synthetic threshold classifier on the extracted total
(<= 12.6 RM -> AUTO_APPROVE, otherwise MANAGER_REVIEW), with the
threshold set at the median of the parsed-total distribution. This is
disclosed openly: the contribution is the verification mechanism, not
the decision rule. The mechanism applies to any OCR-to-decision pipeline.

---

## License

Research prototype. Not for production use.
