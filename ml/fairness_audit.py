"""
Fairness audit — measures who the flight-risk model flags, not just how well.

An HR risk model gets shut down by legal the moment it discriminates against a
protected group, so this audit runs right after scoring, on every pipeline run:

  1. INPUT check: protected attributes (gender, ethnicity_group, age_band)
     must not appear in the model's feature lists. This catches the obvious
     mistake at the source.
  2. OUTCOME check: input-blindness is not enough — tenure, overtime or pay
     features can proxy for protected attributes. So we measure the result:
     the share of each group flagged High risk (the "selection rate"), and
     compare it to the largest group via the disparate-impact ratio

         DI(group) = selection_rate(group) / selection_rate(reference)

     checked against the four-fifths (80%) rule used in US employment law:
     0.80 <= DI <= 1.25.

  3. SIGNIFICANCE adjudication: the four-fifths rule is a screen, not a
     verdict. EEOC guidance is explicit that selection-rate differences
     "based on small numbers" that are "not statistically significant" may
     not constitute adverse impact — a 99-person group needs only a handful
     of extra flags to blow past 1.25 by pure noise. So a group outside the
     band is tested against the reference group with Fisher's exact test:
       * outside band AND p < 0.05  ->  FAIL (the build breaks)
       * outside band AND p >= 0.05 ->  'monitor' (reported, not fatal)
     Groups below MIN_GROUP_N are reported but never judged at all.

     On this dataset the screen genuinely fires — the 55+ band and one
     ethnicity group sit outside four-fifths — and the significance test
     shows both are small-sample noise (p ~ 0.23), while the underlying
     attrition base rates are flat across age. The audit's job is exactly
     this: distinguish a discriminatory model from a small denominator.

The audit is a gate, not a report: a significant disparity makes the script
exit non-zero, which fails CI. Bias becomes a build break.

Output:
    output/fairness_audit.csv   attribute, group, n, selection rate, DI, verdict

Usage:
    python ml/fairness_audit.py     (after engine + attrition_model)
"""

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

sys.path.insert(0, str(ROOT / "ml"))
from attrition_model import CATEGORICAL, NUMERIC  # noqa: E402

PROTECTED = ["gender", "ethnicity_group", "age_band"]
DI_LOW, DI_HIGH = 0.80, 1.25   # four-fifths rule, symmetric
MIN_GROUP_N = 30               # below this, ratios are noise — report, don't judge


def check_model_inputs() -> None:
    leaked = [a for a in PROTECTED if a in set(NUMERIC) | set(CATEGORICAL)]
    if leaked:
        raise SystemExit(f"FAIL: protected attributes in model features: {leaked}")


def audit_frame() -> pd.DataFrame:
    """Scored active employees joined to their protected attributes."""
    scores = pd.read_csv(OUT / "flight_risk_scores.csv",
                         usecols=["employee_id", "risk_band"])
    feats = pd.read_csv(OUT / "flight_risk_features.csv",
                        usecols=["employee_id"] + PROTECTED)
    df = scores.merge(feats, on="employee_id", how="left")
    assert df[PROTECTED].notna().all().all(), "every scored employee needs attributes"
    return df


def selection_rates(df: pd.DataFrame, attribute: str) -> pd.DataFrame:
    g = (df.assign(high=(df["risk_band"] == "High").astype(int))
           .groupby(attribute)
           .agg(n=("high", "size"), n_high=("high", "sum"))
           .reset_index()
           .rename(columns={attribute: "group"}))
    g["attribute"] = attribute
    g["selection_rate"] = g["n_high"] / g["n"]
    ref = g.loc[g["n"].idxmax()]
    g["reference_group"] = ref["group"]
    g["di_ratio"] = g["selection_rate"] / ref["selection_rate"]
    g["evaluated"] = g["n"] >= MIN_GROUP_N

    # Fisher's exact test of each group's high-risk rate vs the reference's.
    pvals = []
    for _, r in g.iterrows():
        table = [[int(r["n_high"]), int(r["n"] - r["n_high"])],
                 [int(ref["n_high"]), int(ref["n"] - ref["n_high"])]]
        pvals.append(fisher_exact(table)[1])
    g["p_value"] = pvals

    in_band = g["di_ratio"].between(DI_LOW, DI_HIGH)
    significant = g["p_value"] < 0.05
    g["verdict"] = "n too small — not judged"
    g.loc[g["evaluated"] & in_band, "verdict"] = "pass"
    g.loc[g["evaluated"] & ~in_band & ~significant,
          "verdict"] = "outside band, not significant — monitor"
    g.loc[g["evaluated"] & ~in_band & significant,
          "verdict"] = "FAIL: significant disparate impact"
    return g


def main() -> pd.DataFrame:
    check_model_inputs()
    df = audit_frame()
    audit = pd.concat([selection_rates(df, a) for a in PROTECTED], ignore_index=True)
    audit = audit[["attribute", "group", "n", "n_high", "selection_rate",
                   "reference_group", "di_ratio", "p_value", "evaluated", "verdict"]]
    audit["selection_rate"] = audit["selection_rate"].round(4)
    audit["di_ratio"] = audit["di_ratio"].round(3)
    audit["p_value"] = audit["p_value"].round(4)
    audit.to_csv(OUT / "fairness_audit.csv", index=False)

    print("FAIRNESS AUDIT - high-risk selection rates by protected group")
    print("=" * 66)
    for attr in PROTECTED:
        sub = audit[audit["attribute"] == attr]
        print(f"\n{attr}  (reference: {sub['reference_group'].iloc[0]})")
        for _, r in sub.iterrows():
            print(f"  {str(r['group']):<14} n={r['n']:>5}  "
                  f"rate={r['selection_rate']:>7.1%}  DI={r['di_ratio']:>6.3f}  "
                  f"p={r['p_value']:>7.4f}  {r['verdict']}")
    print("=" * 66)

    failures = audit[audit["verdict"] == "FAIL: significant disparate impact"]
    if len(failures):
        print(f"\nAUDIT FAILED: {len(failures)} group(s) outside "
              f"[{DI_LOW}, {DI_HIGH}] with p < 0.05 — refusing to ship this score.")
        sys.exit(1)
    watch = audit[audit["verdict"].str.startswith("outside band")]
    if len(watch):
        print(f"\nAudit passed with {len(watch)} group(s) on the monitor list "
              "(outside four-fifths, not statistically significant).")
    else:
        print("\nAll evaluated groups within the four-fifths band. Audit passed.")
    return audit


if __name__ == "__main__":
    main()
