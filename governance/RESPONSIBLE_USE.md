# Responsible-use operating model

The Workforce Decision Room is an aggregate retention-planning product. It is
not an employee-scoring console. The source project keeps synthetic individual
scores so model quality and fairness can be tested, but the live decision
surface publishes only cohorts large enough to review safely.

## Authority boundary

Allowed: prioritise controlled cohort pilots, compare aggregate signals,
monitor outcomes by slice, and prepare questions for qualified HR, privacy and
employment-law review.

Not allowed: rank named employees, automate or recommend an employment action,
use a protected attribute as a decision rule, publish a small group, call a
non-significant disparity “fair,” or present the synthetic intervention lift as
causal evidence.

## Operating cycle

1. **GOVERN** — policy names the decision, model and risk owners; prohibited
   uses and required approvals are machine-readable.
2. **MAP** — each proposal identifies an affected cohort, business signal,
   plausible harm, evidence limit and accountable owner.
3. **MEASURE** — model quality, slice selection rates, uncertainty and privacy
   suppression are recomputed from the pipeline outputs.
4. **MANAGE** — release gates either pass, demand review or block. Every pilot
   carries a monitoring metric and rollback trigger.

This is a practical crosswalk to the NIST AI RMF 1.0 core functions, not a
certification claim. The authoritative framework is published by NIST:
https://doi.org/10.6028/NIST.AI.100-1

The disparate-impact ratio is a screening measure, not a legal conclusion.
The 80% rule reference comes from the Uniform Guidelines Q&A published by the
U.S. Equal Employment Opportunity Commission:
https://www.eeoc.gov/laws/guidance/questions-and-answers-clarify-and-provide-common-interpretation-uniform-guidelines

## Rebuild the evidence

```bash
python governance/build_responsible_use_evidence.py
```

The builder emits canonical CSV, JSON and Markdown artifacts plus SHA-256
digests. CI re-runs it and verifies that no person identifier or individual
risk score reaches the governed release pack.
