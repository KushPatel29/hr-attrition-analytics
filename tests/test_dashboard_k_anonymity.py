"""The k-anonymity claim is about the dashboard, so test the dashboard.

The README says a dashboard filter should never corner one person, and
sql/08_privacy_masking.sql backs that up for the grid it publishes. The Power BI
model did not know about any of it. `Avg Salary` was `AVERAGE(base_salary)` with
nothing in front of it, and the pay equity page plots it by job level and
gender: one of those 27 bubbles was Director x Non-binary, n = 1, at exactly
$190,000. Cross-filter a department and 41 of the 275 cells are single people.

So the floor now lives in the measures, where it applies to any segment a reader
can assemble rather than only the one the SQL precomputed. These tests hold the
two definitions of "too small" together - a threshold that drifts apart between
the SQL and the DAX is the same bug with extra steps - and, more importantly,
prove the guard is not vacuous: if no cell on the shipped data were under the
threshold, every assertion here would pass while protecting nothing.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
MEASURES = (ROOT / "powerbi" / "pbip" / "HRAttritionAnalytics.SemanticModel"
            / "definition" / "tables" / "_Measures.tmdl")
SQL = ROOT / "sql" / "08_privacy_masking.sql"
DATA = ROOT / "data"

# Every measure the SQL treats as sensitive. The SQL suppresses avg_salary,
# avg_compa_ratio and avg_engagement together; the model must not guard two of
# the three and leave the reader to work out which.
GUARDED = ("Avg Salary", "Avg Compa-Ratio", "Avg Engagement")


@pytest.fixture(scope="module")
def tmdl():
    return MEASURES.read_text(encoding="utf-8")


def measure_body(tmdl, name):
    m = re.search(rf"^\tmeasure '{re.escape(name)}' = (.+)$", tmdl, re.M)
    assert m, f"measure '{name}' is missing"
    return m.group(1)


def test_the_threshold_matches_the_sql(tmdl):
    """One K, two implementations. The SQL writes it as `n_active < 5`."""
    dax = int(measure_body(tmdl, "K-Anonymity Threshold"))
    sql_thresholds = {int(n) for n in re.findall(r"n_active\s*<\s*(\d+)", SQL.read_text(encoding="utf-8"))}
    assert sql_thresholds, "sql/08_privacy_masking.sql no longer states a threshold"
    assert sql_thresholds == {dax}, (
        f"DAX suppresses below {dax}, the SQL below {sorted(sql_thresholds)}"
    )


@pytest.mark.parametrize("name", GUARDED)
def test_every_sensitive_measure_is_behind_the_floor(tmdl, name):
    body = measure_body(tmdl, name)
    assert "[K-Anonymity Threshold]" in body and "[Segment Headcount]" in body, (
        f"'{name}' averages a person-level column with no k-anonymity floor - "
        f"filter it to a segment of one and it prints that person's number"
    )


def test_the_headcount_used_by_the_floor_cannot_be_inflated(tmdl):
    """COUNTROWS over a fanned-out relationship would count rows, not people,
    and could lift a cell of one over the threshold."""
    body = measure_body(tmdl, "Segment Headcount")
    assert body.startswith("DISTINCTCOUNT(fact_employees[employee_id])"), body


@pytest.fixture(scope="module")
def segments():
    employees = pd.read_csv(DATA / "fact_employees.csv")
    jobs = pd.read_csv(DATA / "dim_job.csv")[["job_id", "job_level"]]
    return employees.merge(jobs, on="job_id")


def test_the_floor_actually_fires_on_the_shipped_data(segments):
    """Without this the suite would pass on data where nothing needs hiding, and
    the guard would be decorative. This is the cell that made it necessary."""
    cells = segments.groupby(["job_level", "gender"]).size()
    assert (cells < 5).any(), (
        "no job level x gender segment is under the threshold, so the floor in "
        "the model is untested by this dataset"
    )
    assert (cells == 1).any(), "the singleton cell this guard was written for is gone"


def test_a_department_cross_filter_reaches_single_people(segments):
    """The pay equity page is not the only way in - any visual on the page can
    cross-filter the scatter, and department is the obvious one."""
    departments = pd.read_csv(DATA / "dim_department.csv")[["department_id", "department"]]
    cells = segments.merge(departments, on="department_id").groupby(
        ["department", "job_level", "gender"]).size()
    assert (cells == 1).sum() > 0, (
        "no single-person cell under a department cross-filter - the guard is "
        "protecting nothing on this dataset"
    )


def test_the_visual_says_that_small_segments_are_withheld():
    """A bubble that vanishes with no explanation is its own kind of misleading."""
    scatter = (ROOT / "powerbi" / "pbip" / "HRAttritionAnalytics.Report" / "definition"
               / "pages" / "section_payequity" / "visuals" / "visual4006" / "visual.json")
    text = scatter.read_text(encoding="utf-8")
    assert "withheld" in text and "k-anonymity" in text.lower(), (
        "the pay equity scatter drops segments under the threshold without "
        "telling the reader it did"
    )
