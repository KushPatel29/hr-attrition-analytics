"""Rendered Streamlit smoke tests for the governed decision room."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def test_app_renders_without_exception(app):
    assert not app.exception


def test_app_exposes_five_decision_workspaces(app):
    assert [tab.label for tab in app.tabs] == [
        "Release decision",
        "Intervention portfolio",
        "Workforce signals",
        "Fairness & privacy",
        "Evidence map",
    ]


def test_workforce_metrics_reconcile_to_pipeline(app):
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Active headcount"] == "2,151"
    assert values["Trailing-12-month attrition"] == "20.6%"
    assert values["Regretted salary exposure"] == "$11.1M"
    assert values["Chosen model ROC-AUC"] == "0.738"


def test_interactions_start_at_aggregate_scopes(app):
    selectors = {selectbox.label: selectbox.value for selectbox in app.selectbox}
    assert selectors["Proposal to review"].startswith("RET-")
    assert selectors["Slice family"] in {"age_band", "ethnicity_group", "gender"}
