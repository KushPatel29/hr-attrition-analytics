"""Survival-analysis invariants: curves behave like survival curves, censoring
is real, and the Cox model recovers the planted attrition drivers."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DOCS = ROOT / "docs"


def _curves():
    return pd.read_csv(OUT / "survival_curves.csv")


def test_outputs_exist():
    for f in ["survival_curves.csv", "survival_medians.csv", "cox_hazard_ratios.csv"]:
        assert (OUT / f).exists(), f"missing {f}"
    assert (DOCS / "survival_curves.png").exists()


def test_every_curve_is_a_survival_curve():
    c = _curves()
    assert c["survival_prob"].between(0, 1).all()
    for (_, _), grp in c.groupby(["group_type", "group"]):
        grp = grp.sort_values("tenure_months")
        assert grp["survival_prob"].iloc[0] == 1.0, "S(0) must be 1"
        assert grp["survival_prob"].is_monotonic_decreasing or \
            (grp["survival_prob"].diff().dropna() <= 1e-9).all()


def test_censoring_is_real():
    m = pd.read_csv(OUT / "survival_medians.csv")
    overall = m[m["group_type"] == "overall"].iloc[0]
    # far more censored (active + involuntary) than events, and never zero events
    assert 0 < overall["events"] < overall["n"] * 0.5
    # median survival should NOT be reached at ~16% voluntary attrition —
    # if it suddenly is, either the data or the event definition broke
    assert pd.isna(overall["median_months"])


def test_engagement_bands_order_correctly():
    m = pd.read_csv(OUT / "survival_medians.csv")
    eng = m[m["group_type"] == "engagement_band"].set_index("group")
    low = eng.loc["Engagement < 60", "t25_months"]
    mid = eng.loc["Engagement 60-75", "t25_months"]
    high = eng.loc["Engagement 75+", "t25_months"]
    assert pd.notna(low) and pd.notna(mid)
    assert low < mid, "less engaged cohorts must lose 25% sooner"
    assert pd.isna(high) or high > mid


def test_cox_recovers_planted_drivers():
    cox = pd.read_csv(OUT / "cox_hazard_ratios.csv").set_index("covariate")
    eng = cox.loc["engagement_score"]
    stag = cox.loc["promo_stagnation_share"]
    assert eng["hazard_ratio_per_sd"] < 1 and eng["p_value"] < 0.05, \
        "engagement must be significantly protective"
    assert stag["hazard_ratio_per_sd"] > 1 and stag["p_value"] < 0.05, \
        "promotion stagnation must be a significant hazard"
    # CI sanity: bounds bracket the point estimate
    assert (cox["hr_ci_low"] <= cox["hazard_ratio_per_sd"]).all()
    assert (cox["hr_ci_high"] >= cox["hazard_ratio_per_sd"]).all()


def test_no_protected_attributes_in_cox():
    cox = pd.read_csv(OUT / "cox_hazard_ratios.csv")
    protected = {"gender", "ethnicity_group", "age_band"}
    assert not set(cox["covariate"]) & protected
