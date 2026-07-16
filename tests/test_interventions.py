"""Intervention-loop invariants: the log is referentially sound, the SQL
cohort matches the generator's targeting rule, and the analysis recovers the
planted retention effect."""
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"
sys.path.insert(0, str(ROOT / "data_generator"))

from generate_interventions import (  # noqa: E402
    COMPA_LT, ENGAGEMENT_LT, MIN_RUNWAY_DAYS, MONTHS_SINCE_PROMO_GT, SNAPSHOT,
    at_risk,
)


def _log():
    return pd.read_csv(DATA / "fact_hr_interventions.csv",
                       parse_dates=["intervention_date"])


def _emp():
    return pd.read_csv(DATA / "fact_employees.csv",
                       parse_dates=["hire_date", "termination_date"])


def test_log_referential_integrity():
    log, emp = _log(), _emp()
    assert log["intervention_id"].is_unique
    assert log["employee_id"].is_unique, "one intervention per employee in v1"
    assert log["employee_id"].isin(emp["employee_id"]).all()


def test_intervention_dates_inside_employment():
    log, emp = _log(), _emp()
    m = log.merge(emp, on="employee_id")
    end = m["termination_date"].fillna(SNAPSHOT)
    assert (m["intervention_date"] >= m["hire_date"] + pd.Timedelta(days=90)).all()
    assert (m["intervention_date"] <= end).all()


def test_only_at_risk_employees_treated():
    log, emp = _log(), _emp()
    treated = emp[emp["employee_id"].isin(log["employee_id"])]
    assert at_risk(treated).all(), "intervention on a non-at-risk employee"


def test_sql_cohort_matches_generator_rule():
    """sql/09 re-states the targeting rule in SQL; if the two definitions
    drift apart the whole comparison silently rots. Rebuild the cohort in
    pandas from the generator's constants and match the SQL row counts."""
    emp, log = _emp(), _log()
    eff = pd.read_csv(OUT / "intervention_effectiveness.csv")

    end = emp["termination_date"].fillna(SNAPSHOT)
    runway_ok = (end - emp["hire_date"]).dt.days >= MIN_RUNWAY_DAYS
    cohort = emp[at_risk(emp) & (emp["term_type"] != "Involuntary") & runway_ok]
    treated = cohort["employee_id"].isin(log["employee_id"])

    sql_control = eff.loc[eff["cohort_label"] == "No intervention (control)"].iloc[0]
    sql_any = eff.loc[eff["cohort_label"] == "Any intervention"].iloc[0]
    assert sql_control["n_employees"] == int((~treated).sum())
    assert sql_any["n_employees"] == int(treated.sum())
    # thresholds referenced here so a constant change breaks this test loudly
    assert (ENGAGEMENT_LT, COMPA_LT, MONTHS_SINCE_PROMO_GT) == (60, 0.85, 24)


def test_planted_effect_recovered_and_significant():
    eff = pd.read_csv(OUT / "intervention_effectiveness.csv")
    ctrl = eff.loc[eff["cohort_label"] == "No intervention (control)"].iloc[0]
    any_ = eff.loc[eff["cohort_label"] == "Any intervention"].iloc[0]
    assert any_["lift_vs_control"] > 0.05, "planted lift not recovered"
    table = [[int(any_["n_retained"]), int(any_["n_employees"] - any_["n_retained"])],
             [int(ctrl["n_retained"]), int(ctrl["n_employees"] - ctrl["n_retained"])]]
    assert fisher_exact(table)[1] < 0.05, "recovered lift should be significant"


def test_effectiveness_table_shape():
    eff = pd.read_csv(OUT / "intervention_effectiveness.csv")
    ctrl = eff[eff["sort_order"] == 0]
    assert len(ctrl) == 1 and ctrl["lift_vs_control"].isna().all()
    assert eff["retention_rate"].between(0, 1).all()
    per_type = eff[eff["sort_order"] == 2]
    any_n = eff.loc[eff["cohort_label"] == "Any intervention", "n_employees"].iloc[0]
    assert per_type["n_employees"].sum() == any_n
