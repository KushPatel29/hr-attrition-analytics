"""SQL engine invariants: the analytics the dashboard depends on stay correct."""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def _read(name):
    return pd.read_csv(OUT / f"{name}.csv")


def test_all_outputs_exist():
    for name in ["workforce_kpis", "headcount_bridge", "attrition_by_dimension",
                 "retention_cohorts", "pay_equity", "pay_equity_levels",
                 "funnel_stages", "recruiting_by_source", "recruiting_kpis",
                 "flight_risk_features"]:
        assert (OUT / f"{name}.csv").exists(), f"missing {name}.csv"


def test_workforce_kpis_sane():
    k = _read("workforce_kpis")
    # ramp-up months can be zero; headcount is never negative and ends healthy
    assert (k["headcount"] >= 0).all()
    assert k["headcount"].iloc[-1] > 1000
    assert k["month"].is_monotonic_increasing
    r = k["rolling_12m_attrition_rate"].dropna()
    assert ((r >= 0) & (r <= 1)).all()


def test_headcount_bridge_balances():
    b = _read("headcount_bridge").sort_values("sort_order")
    begin, hires, terms = b["value"].tolist()
    assert hires > 0 and terms < 0 and begin > 0
    # running total of the three deltas equals the current headcount
    end = begin + hires + terms
    latest_headcount = _read("workforce_kpis").iloc[-1]["headcount"]
    assert end == latest_headcount, "bridge total should equal current headcount"


def test_funnel_monotone_non_increasing():
    f = _read("funnel_stages").sort_values("stage_order")
    cand = f["candidates"].tolist()
    assert all(cand[i] >= cand[i + 1] for i in range(len(cand) - 1))
    hired_conv = f.loc[f["stage"] == "Hired", "overall_conversion"].iloc[0]
    assert 0 < hired_conv < 1


def test_retention_curve_declines_and_bounded():
    r = _read("retention_cohorts")
    allc = r[r["cohort_year"] == "All"].sort_values("months_since_hire")
    assert allc["retention_rate"].between(0, 1).all()
    assert allc.iloc[0]["months_since_hire"] == 0
    assert allc.iloc[0]["retention_rate"] == pytest.approx(1.0)
    # overall trend declines from month 0 to the last milestone
    assert allc.iloc[-1]["retention_rate"] < allc.iloc[0]["retention_rate"]


def test_pay_equity_has_adjusted_rollup():
    p = _read("pay_equity")
    roll = p[p["job_level"] == "ALL (level-adjusted)"]
    assert len(roll) == 1
    assert roll["raw_gap_pct"].between(-1, 1).all()
    assert (p["n_female"] + p["n_male"] > 0).all()


def test_attrition_dimensions_present_and_bounded():
    a = _read("attrition_by_dimension")
    dims = set(a["dimension"].unique())
    assert {"Department", "Division", "Job Level", "Region",
            "Gender", "Age Band", "Tenure Band"}.issubset(dims)
    assert a["attrition_rate"].between(0, 1).all()


def test_flight_risk_features_target():
    ff = _read("flight_risk_features")
    assert ff["left_flag"].isin([0, 1]).all()
    assert "engagement_vs_dept" in ff.columns
    assert "comp_gap_vs_level" in ff.columns
