"""ML gate: the shipped model must beat the baseline and clear a useful bar."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def test_model_evaluation_present():
    assert (OUT / "model_evaluation.csv").exists()


def test_exactly_one_chosen_model():
    ev = pd.read_csv(OUT / "model_evaluation.csv")
    assert ev["is_chosen"].sum() == 1


def test_chosen_beats_baseline_and_clears_bar():
    ev = pd.read_csv(OUT / "model_evaluation.csv")
    baseline = ev[ev["model"].str.contains("Baseline")]["roc_auc"].iloc[0]
    chosen = ev[ev["is_chosen"] == 1].iloc[0]
    assert chosen["roc_auc"] > baseline + 0.05, "chosen model barely beats baseline"
    assert chosen["roc_auc"] >= 0.68, f"chosen ROC-AUC {chosen['roc_auc']} below gate"
    assert chosen["lift_at_decile"] > 1.3, "top-decile lift not actionable"


def test_scores_valid():
    s = pd.read_csv(OUT / "flight_risk_scores.csv")
    assert s["risk_score"].between(0, 1).all()
    assert s["risk_band"].isin(["High", "Medium", "Low"]).all()
    assert s["employee_id"].is_unique


def test_all_active_employees_scored():
    s = pd.read_csv(OUT / "flight_risk_scores.csv")
    emp = pd.read_csv(ROOT / "data" / "fact_employees.csv",
                      keep_default_na=False, na_values=[])
    active = int((emp["is_active"] == 1).sum())
    assert len(s) == active, "every active employee should be scored exactly once"


def test_high_band_is_top_slice():
    s = pd.read_csv(OUT / "flight_risk_scores.csv")
    high_share = (s["risk_band"] == "High").mean()
    assert 0.10 <= high_share <= 0.20, f"High band share {high_share:.2f} unexpected"
