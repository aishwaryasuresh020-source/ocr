python3 <<'PYEOF'
from pathlib import Path

content = '''# COMPLETE SPECIFICATION

## TITLE OF THE INVENTION

DECISION-IMPACT-AWARE DETECTION AND MINIMUM-COST DECISION-STABILIZING VERIFICATION IN OCR-TO-DECISION PIPELINES

---

## FIELD OF THE INVENTION

The present invention relates generally to computer-implemented systems for processing optical character recognition (OCR) output. More particularly, the invention relates to a system and method for detecting semantic corruption in OCR-derived information based on its potential impact on a downstream automated decision, and for determining and executing a minimum-cost set of verification actions required to render the downstream decision invariant to remaining semantic uncertainty.

---

## BACKGROUND OF THE INVENTION

Optical character recognition (OCR) systems are widely deployed to convert scanned documents, receipts, invoices, and forms into machine-readable text. The output of such systems is increasingly consumed not merely by humans, but by automated decision pipelines, for example invoice approval workflows, insurance claim triage systems, and financial transaction processing engines.

A fundamental problem exists in the interface between OCR systems and automated decision systems. Conventional OCR verification methods assess accuracy at the character level, rely on confidence scores, employ dictionaries or syntactic validation, or apply general document-quality measures. These methods do not adequately distinguish between OCR errors that are harmless to a downstream decision and errors that can alter the final decision.

Consider a concrete example. An invoice amount is incorrectly recognized by an OCR engine as 18,500 instead of the true value 48,500. Both values are syntactically valid, both parse as monetary amounts, and both may carry similar OCR confidence scores. However, if the downstream decision rule is:

    Amount <= 20,000  -> Auto Approve
    Amount >  20,000  -> Manager Review

then the OCR error changes the final decision. A confidence-based verification system would have no principled basis to prioritize this field over another field with similar confidence whose value cannot affect the decision.

The limitations of existing systems include: (a) a lack of downstream decision awareness, such that verification effort is not directed by decision impact; (b) an inability to identify decision-critical semantic corruption; (c) no systematic evaluation of alternative OCR interpretations through the decision function; (d) verification of uncertain fields without regard to whether those fields can actually change the decision; and (e) fixed verification workflows that do not terminate when the decision becomes stable.

There is therefore a need for a system that detects OCR-induced uncertainty according to its potential to alter a downstream decision, evaluates the space of plausible interpretations against that decision, and determines the minimum set of verification actions required to guarantee decision stability.

---

## SUMMARY OF THE INVENTION

The present invention provides a computer-implemented system and method that solve the above-identified technical problem.

In one aspect, the invention provides a computer-implemented system for stabilizing automated decisions derived from OCR output. The system comprises a memory and a processor configured to execute a plurality of modules.

A field extraction module extracts a set of semantic fields from OCR output of a document. Each extracted field is associated with provenance data comprising a source token and an OCR confidence value.

A dependency graph construction module builds a Decision Dependency Graph. The graph comprises a declarative mapping from each semantic field to one or more named conditions of a downstream decision function, and a set of condition evaluators derived from the decision function.

An uncertainty detection module identifies, for each extracted field, a semantic uncertainty based at least on the OCR confidence of its source token or on a format ambiguity of the source token.

A candidate generation module generates, for each uncertain field that is determined to be decision-relevant according to the Decision Dependency Graph, a set of constrained counterfactual interpretations. The interpretations are constrained by OCR confusion patterns, format rules, and structural plausibility. When the OCR confidence of a decision-relevant field is below a threshold, or when the field is missing, the candidate set is augmented with probe values spanning a decision boundary of the downstream decision function.

An impact scoring module computes a Counterfactual Decision Impact Score for each uncertain field by evaluating the downstream decision function on the counterfactual interpretations and computing a normalized weighted entropy over the resulting decision labels.

A verification optimization module determines a minimum-cost verification set V* by solving a constrained optimization problem that minimizes a total verification cost over subsets V of the uncertain fields, subject to a decision-invariance constraint. The decision-invariance constraint requires that every remaining interpretation of the unverified uncertain fields yields the same downstream decision after the fields in V have been replaced with verified values.

An adaptive verification module executes verification actions on the fields in V* and terminates verification automatically when the downstream decision becomes invariant.

In another aspect, the invention provides a corresponding computer-implemented method and a non-transitory computer-readable medium storing instructions for performing the method.

The technical effect of the invention is a measurable reduction in verification operations and associated computational resource consumption, while preserving downstream decision accuracy. In an experimental evaluation on the SROIE dataset comprising 973 invoices, the invention reduced verification cost by approximately 62.5 percent compared to a baseline that verifies every uncertain field, while achieving identical decision accuracy on the test split.

---

## DETAILED DESCRIPTION OF THE INVENTION

### 1. System Architecture

The system comprises a pipeline of interconnected modules, each implemented as computer-executable instructions stored in a memory and executed by one or more processors. The modules are:

1. Preprocessing module - parses document annotations and ground-truth data into a structured format.
2. OCR engine module - invokes an OCR engine on document images and produces word-level output comprising text, confidence, and bounding box coordinates.
3. Field extraction module - reconstructs OCR lines and extracts semantic fields (company, date, address, total) with provenance.
4. Decision module - defines a downstream decision function and a verification cost table.
5. Uncertainty detection module - flags fields as uncertain based on OCR confidence and format ambiguity.
6. Candidate generation module - produces constrained counterfactual interpretations of uncertain fields.
7. Dependency graph module - constructs the Decision Dependency Graph.
8. Impact scoring module - computes Counterfactual Decision Impact Scores.
9. Minimum verification module - solves the constrained optimization problem to determine V*.
10. Adaptive verification module - executes sequential verification with decision-invariant termination.
11. Evaluation module - runs the pipeline against baselines and computes metrics.

### 2. Field Extraction with Provenance

The field extraction module reconstructs lines from word-level OCR output by grouping words according to block, paragraph, and line identifiers, and sorting words within each line by horizontal position. Semantic fields are extracted by rule-based heuristics applied to the reconstructed lines.

Each extracted field is stored together with provenance data. The provenance data comprises at least: the extracted value; the raw OCR source token; the reconstructed line text; the line index; the constituent word objects with their OCR confidence values; and an aggregate confidence computed as the minimum valid confidence among the constituent words.

The provenance data is essential to the invention because it enables downstream modules to assess uncertainty from the specific OCR content that produced the field, and to generate constrained counterfactual interpretations of that specific content.

### 3. Downstream Decision Function

The downstream decision function maps the extracted semantic fields to a discrete decision label. In a preferred embodiment, the decision function is a threshold classifier on the extracted total:

    If the total is missing or unparseable -> decision label REVIEW
    If the total <= a threshold T          -> decision label AUTO_APPROVE
    Otherwise                              -> decision label MANAGER_REVIEW

The threshold T is selected based on the distribution of the target field in the document corpus. In the experimental embodiment, T was set at the median of the parsed-total distribution on the SROIE training split (T = 12.6 RM).

The decision function also exposes a set of named conditions such as total_present and total_le_threshold, which serve as the anchors for the Decision Dependency Graph.

The system further comprises a verification cost table that assigns a cost to the verification of each field. In the experimental embodiment: company = 1, date = 1, address = 3, total = 2.

### 4. Uncertainty Detection

The uncertainty detection module receives the extracted fields and their provenance data and produces a set of uncertain fields. Each uncertain field is annotated with a reason and a numeric uncertainty score in the range zero to one.

Uncertainty is detected from at least the following sources:

(a) Low OCR confidence. If the aggregate confidence of a field source words falls below a low-confidence threshold (e.g., 70), the field is flagged with a high uncertainty score. If the confidence falls between the low-confidence threshold and a medium-confidence threshold (e.g., 85), the field is flagged with a moderate uncertainty score.

(b) Ambiguous money separator. If a monetary source token contains a comma but no period, the separator is ambiguous between a decimal comma and a thousands separator, and the field is flagged.

(c) Ambiguous date order. If a date source token has both leading components at most twelve, the day/month ordering is ambiguous, and the field is flagged.

(d) Missing field. If the extraction module returns no value for a field, the field is flagged with maximum uncertainty.

### 5. Constrained Counterfactual Interpretation Generation

The candidate generation module receives an uncertain field and its source token and produces a small set of plausible alternative interpretations. Each candidate comprises a value, a reason label, and a plausibility weight.

(a) Money candidates. For a monetary source token, candidates are generated by taking the as-is interpretation; reinterpreting the separator; and applying single-character OCR confusion substitutions from a confusion table. Candidates are deduplicated by value. Weights reflect plausibility: as-is is 1.0; format reinterpretation is 0.3 to 0.4; character confusion is 0.35.

(b) Date candidates. For a date source token, the as-is interpretation is always included. If both leading components are at most twelve, a day/month swap candidate is generated with weight 0.6.

(c) Text candidates. For text fields that do not enter the decision function, only the as-is interpretation is generated.

(d) Probe augmentation for decision-relevant fields. For a decision-relevant field, if the OCR confidence is below a threshold or if the field is missing, the candidate set is augmented with probe values that span the decision boundary. In the experimental embodiment, for the numeric total field, the probes are a value below the threshold and a value above the threshold. This augmentation is essential: without it, a decision-relevant field that is confidently misread, or entirely missing, would trivially satisfy the invariance check and wrongly skip verification.

### 6. Decision Dependency Graph

The dependency graph module constructs a data structure that maps each semantic field to the named conditions of the decision function that the field can influence. The conditions are imported directly from the decision module, ensuring that the graph and the decision function cannot drift out of synchronization.

In the experimental embodiment, the graph is:

    total   -> total_present, total_le_threshold
    company -> (none)
    date    -> (none)
    address -> (none)

A field with no path to any decision condition cannot change the decision regardless of its uncertainty.

### 7. Counterfactual Decision Impact Scoring

The impact scoring module computes, for each uncertain field, a Counterfactual Decision Impact Score.

For a field that is not decision-relevant according to the graph, the impact is zero regardless of its uncertainty.

For a field that is decision-relevant, each candidate is substituted into a copy of the field set, and the downstream decision function is evaluated. A weighted entropy is computed over the decision labels, using candidate weights as probabilities. The entropy is normalized by the logarithm of the number of possible decision labels to produce a score in the range zero to one.

If all candidates produce the same decision label, the impact is zero. If candidates produce different decision labels, the impact is greater than zero. For a missing decision-relevant field, the impact is one.

### 8. Minimum-Cost Decision-Stabilizing Verification Set

The minimum verification module determines a minimum-cost verification set V*. Given the set U of uncertain fields, candidate value lists, a ground-truth value for each field, and a cost table, the module solves:

    V* = argmin over V subset of U of Cost(V)

    subject to: for every combination of remaining candidate values, after replacing the fields in V with ground-truth values, the downstream decision function yields the same decision label.

The optimization is solved by exhaustive enumeration of subsets of U in order of increasing size. For each subset V, the module constructs a verified field set and checks the decision-invariance constraint. The cheapest subset that satisfies the constraint is returned.

### 8b. Formal Minimality Proof

Definitions. Let U be the finite set of uncertain semantic fields. Let C be an additive, non-negative cost function. Let D be the downstream decision function. Let cand(f) be the finite set of candidate values for field f. Let GT(f) be the ground-truth value for f. Let Invariant(V) be the predicate that for all combinations of remaining candidate values, after substituting GT for V, the decision is a single label.

Problem. Determine V* = argmin over feasible V of C(V).

Algorithm. Enumerate subsets V of U in increasing order of cardinality. For each V, evaluate Invariant(V) and compute C(V). Return the subset with minimum C(V) among those where Invariant(V) holds.

Proof.

1. Termination. U is finite. GT(f) is available for every f in U, so after verifying all of U there are no remaining uncertain fields and Invariant(U) is trivially true. At least one feasible V exists.

2. Optimality. Suppose for contradiction that the algorithm returns V* but there exists V prime with Invariant(V prime) true and C(V prime) < C(V*). Since the algorithm enumerates every subset, V prime is evaluated. When V prime is evaluated, Invariant(V prime) is true, so V prime is a candidate. If C(V prime) < C(V*), the algorithm replaces V*. Contradiction.

3. Ties. If multiple subsets achieve the minimum cost, the algorithm returns the first in enumeration order, giving a deterministic result.

Complexity. The enumeration visits 2 raised to the power of |U| subsets. For |U| at most four, as in the experimental embodiment, at most sixteen subsets per invoice. For larger |U|, the sequential greedy variant selects the highest-impact and lowest-cost field at each step.

Empirical confirmation. Across 973 invoices, all evaluations terminated with Invariant(V*) true and the measured accuracy matched the exhaustive-verification baseline.

### 9. Impact-Driven Adaptive Sequential Verification

In an alternative embodiment, the verification is performed sequentially. At each step:

1. Check whether the decision is already invariant under the remaining uncertainty. If so, terminate.
2. Select the next field to verify by ranking the remaining uncertain fields by descending impact score and, as a tie-break, ascending verification cost.
3. Substitute the ground-truth value for the selected field.
4. Remove the field from the remaining uncertain set.
5. Return to step 1.

The output is a trace of verification actions, each comprising the field verified, its impact score, its cost, the decision after verification, and whether the decision became invariant after that action.

### 10. Experimental Results and Proof of Technical Effect

The system was evaluated on the SROIE 2019 dataset, comprising 626 training invoices and 347 test invoices. Five verification strategies were compared:

    Method                 Train Acc  Train Cost  Test Acc  Test Cost
    Verify Nothing            59.6%       0.000     61.7%      0.000
    Verify by Confidence      65.5%       3.401     67.1%      3.242
    Verify All Uncertain      88.3%       5.412     89.9%      5.398
    Verify All Fields         91.4%       7.000     92.8%      7.000
    Adaptive (This System)    88.3%       2.042     89.9%      2.026

The present invention achieves identical decision accuracy to the Verify All Uncertain baseline on both splits, while reducing the average verification cost by approximately 62.5 percent (from 5.398 to 2.026 on the test split). It improves upon OCR-confidence-based verification by approximately 22.8 accuracy points on the test split at approximately 38 percent lower cost.

This constitutes a concrete, quantifiable technical effect: a reduction in the number of verification operations and associated computational resource consumption, while preserving downstream decision accuracy. This is a measurable system-level impact of the kind recognized as a technical effect in the 2025 CRI Guidelines and in Ferid Allani v. Union of India.

### 11. Limitations and Disclosed Embodiments

High-confidence OCR misreads, where the OCR engine produces an incorrect value with high confidence, are not detected by the uncertainty detection module in the current embodiment. This is a limitation of the uncertainty detector, not of the decision-stabilizing verification mechanism. A future embodiment could integrate a cross-field consistency check.

The candidate generation module in the current embodiment generates format-based interpretations and single-character confusion substitutions. It does not model arbitrary digit substitution.

The system has been described with reference to a receipt-processing application. It is to be understood that the system is applicable to any OCR-to-decision pipeline, including invoice approval, insurance claim triage, prescription verification, and financial transaction processing. The application domain is not limiting.

---

## ABSTRACT

A computer-implemented system and method for stabilizing automated decisions derived from optical character recognition (OCR) output. The system extracts semantic fields with provenance data, constructs a Decision Dependency Graph linking fields to conditions of a downstream decision function, detects semantic uncertainty based on OCR confidence and format ambiguity, generates constrained counterfactual interpretations of uncertain decision-relevant fields including probe values spanning a decision boundary, computes a Counterfactual Decision Impact Score, determines a minimum-cost verification set by solving a constrained optimization problem that minimizes verification cost subject to a decision-invariance constraint, and executes verification actions until the downstream decision becomes invariant. In an experimental evaluation on 973 invoices, the system achieved identical decision accuracy to a verify-all-uncertain baseline while reducing verification cost by approximately 62.5 percent.
'''

Path("docs/specification.md").write_text(content, encoding="utf-8")
print("Wrote docs/specification.md:", len(content.splitlines()), "lines")
PYEOF