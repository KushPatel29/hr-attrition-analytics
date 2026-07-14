"""Data-generation invariants: schema, referential integrity, value ranges."""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def emp():
    return pd.read_csv(DATA / "fact_employees.csv", keep_default_na=False, na_values=[])


def test_expected_columns(emp):
    expected = {
        "employee_id", "department_id", "job_id", "location_id", "gender",
        "ethnicity_group", "age_band", "hire_date", "termination_date",
        "term_type", "is_active", "tenure_months", "base_salary", "compa_ratio",
        "performance_rating", "engagement_score", "overtime_hours", "commute_km",
        "months_since_promotion", "manager_id", "tenure_band",
    }
    assert expected.issubset(set(emp.columns))


def test_unique_employee_ids(emp):
    assert emp["employee_id"].is_unique


def test_referential_integrity(emp):
    dept = pd.read_csv(DATA / "dim_department.csv")
    job = pd.read_csv(DATA / "dim_job.csv")
    loc = pd.read_csv(DATA / "dim_location.csv")
    assert emp["department_id"].isin(dept["department_id"]).all()
    assert emp["job_id"].isin(job["job_id"]).all()
    assert emp["location_id"].isin(loc["location_id"]).all()


def test_value_ranges(emp):
    assert emp["is_active"].isin([0, 1]).all()
    assert (emp["tenure_months"] >= 0).all()
    assert emp["performance_rating"].between(1, 5).all()
    assert emp["engagement_score"].between(0, 100).all()
    assert (emp["base_salary"] > 0).all()


def test_active_and_terminated_consistency(emp):
    active = emp[emp["is_active"] == 1]
    left = emp[emp["is_active"] == 0]
    # active have no termination date; terminated have one and a term_type
    assert (active["termination_date"] == "").all()
    assert (left["termination_date"] != "").all()
    assert left["term_type"].isin(["Voluntary", "Involuntary"]).all()


def test_separation_rate_realistic(emp):
    # deterministic seed -> stable band across numpy versions
    assert len(emp) == 1900
    sep_rate = (emp["is_active"] == 0).mean()
    assert 0.15 <= sep_rate <= 0.30, f"separation rate {sep_rate:.3f} out of expected band"


def test_recruiting_funnel_monotone_at_source():
    apps = pd.read_csv(DATA / "fact_applications.csv", keep_default_na=False, na_values=[])
    # each stage flag implies the previous one
    reached_interview = apps["reached_interview"] == 1
    reached_screen = apps["reached_screen"] == 1
    assert (reached_interview <= reached_screen).all()
