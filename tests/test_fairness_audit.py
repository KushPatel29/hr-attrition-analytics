"""Fairness invariants: protected attributes stay out of the model, and the
disparate-impact gate both passes honest scores and catches planted bias."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
sys.path.insert(0, str(ROOT / "ml"))

from attrition_model import CATEGORICAL, NUMERIC  # noqa: E402
from fairness_audit import PROTECTED, selection_rates  # noqa: E402


def test_protected_attributes_not_model_inputs():
    features = set(NUMERIC) | set(CATEGORICAL)
    assert not features & set(PROTECTED), "protected attributes leaked into the model"


def test_no_protected_features_in_importance_table():
    imp = pd.read_csv(OUT / "feature_importance.csv")
    for attr in PROTECTED:
        assert not imp["feature"].str.startswith(attr).any()


def test_audit_covers_all_scored_employees():
    audit = pd.read_csv(OUT / "fairness_audit.csv")
    scores = pd.read_csv(OUT / "flight_risk_scores.csv")
    assert set(audit["attribute"]) == set(PROTECTED)
    for attr in PROTECTED:
        assert audit.loc[audit["attribute"] == attr, "n"].sum() == len(scores)


def test_no_significant_disparate_impact_shipped():
    """The CI gate in script form: the shipped scores must not contain a
    statistically significant four-fifths violation."""
    audit = pd.read_csv(OUT / "fairness_audit.csv")
    fails = audit[audit["verdict"] == "FAIL: significant disparate impact"]
    assert len(fails) == 0, fails.to_string()


def test_di_ratio_math():
    df = pd.DataFrame({
        "risk_band": ["High"] * 20 + ["Low"] * 80 + ["High"] * 10 + ["Low"] * 90,
        "grp": ["A"] * 100 + ["B"] * 100,
    })
    out = selection_rates(df, "grp").set_index("group")
    # A is not larger than B, so reference is whichever idxmax picked (equal n);
    # ratios must be exact either way.
    ra, rb = out.loc["A", "selection_rate"], out.loc["B", "selection_rate"]
    assert ra == 0.20 and rb == 0.10
    ref = out["reference_group"].iloc[0]
    expected = {g: out.loc[g, "selection_rate"] / out.loc[ref, "selection_rate"]
                for g in ["A", "B"]}
    assert np.isclose(out.loc["A", "di_ratio"], expected["A"])
    assert np.isclose(out.loc["B", "di_ratio"], expected["B"])


def test_gate_catches_planted_bias():
    """A large group selected at 3x the reference rate must FAIL."""
    rng = np.random.default_rng(0)
    n = 800
    grp = np.array(["Ref"] * n + ["Target"] * n)
    p = np.where(grp == "Ref", 0.10, 0.30)
    band = np.where(rng.random(2 * n) < p, "High", "Low")
    df = pd.DataFrame({"risk_band": band, "grp": grp})
    out = selection_rates(df, "grp").set_index("group")
    assert out.loc["Target", "verdict"] == "FAIL: significant disparate impact"


def test_gate_ignores_small_sample_noise():
    """A tiny group with a wild ratio is reported, never judged."""
    df = pd.DataFrame({
        "risk_band": ["High"] * 3 + ["Low"] * 7 + ["High"] * 100 + ["Low"] * 900,
        "grp": ["Tiny"] * 10 + ["Ref"] * 1000,
    })
    out = selection_rates(df, "grp").set_index("group")
    assert out.loc["Tiny", "verdict"] == "n too small — not judged"
