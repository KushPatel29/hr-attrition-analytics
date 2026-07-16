"""k-anonymity invariants: small segments can never leak individual comp data."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DATA = ROOT / "data"

K = 5
METRICS = ["avg_salary", "avg_compa_ratio", "avg_engagement"]


def _masked():
    return pd.read_csv(OUT / "masked_segment_metrics.csv")


def test_outputs_exist():
    assert (OUT / "masked_segment_metrics.csv").exists()
    assert (OUT / "privacy_suppression_audit.csv").exists()


def test_no_published_cell_below_k():
    m = _masked()
    pub = m[m["suppression"] == "published"]
    assert len(pub) > 0
    assert (pub["n_band"].astype(int) >= K).all()
    assert pub[METRICS].notna().all().all()


def test_suppressed_cells_carry_no_metrics():
    m = _masked()
    sup = m[m["suppression"] != "published"]
    assert len(sup) > 0, "the rule should actually fire on this dataset"
    assert sup[METRICS].isna().all().all()
    # small cells must not publish an exact headcount either
    primary = sup[sup["suppression"].str.contains("n < 5")]
    assert (primary["n_band"] == "<5").all()


def test_two_cell_rule_no_recoverable_singles():
    """If only one cell in a dept x level group were hidden, subtraction from
    the group roll-up would recover it. Every group with any suppression (and
    more than one cell) must therefore hide at least two."""
    m = _masked()
    g = m.groupby(["department", "job_level"]).agg(
        cells=("gender", "size"),
        suppressed=("suppression", lambda s: int((s != "published").sum())),
    )
    bad = g[(g["suppressed"] == 1) & (g["cells"] > 1)]
    assert len(bad) == 0, f"recoverable single-suppression groups: {bad.index.tolist()}"


def test_published_values_match_source():
    """Masking must not distort what it publishes: spot-check every published
    cell's avg salary against a direct aggregation of the source data."""
    m = _masked()
    emp = pd.read_csv(DATA / "fact_employees.csv")
    dept = pd.read_csv(DATA / "dim_department.csv")
    job = pd.read_csv(DATA / "dim_job.csv")
    emp = emp[emp["is_active"] == 1].merge(dept, on="department_id").merge(job, on="job_id")
    truth = (emp.groupby(["department", "job_level", "gender"])["base_salary"]
             .agg(["size", "mean"]).reset_index())

    pub = m[m["suppression"] == "published"].merge(
        truth, on=["department", "job_level", "gender"], how="left")
    assert pub["mean"].notna().all()
    assert (pub["n_band"].astype(int) == pub["size"]).all()
    assert (pub["avg_salary"] - pub["mean"].round(0)).abs().max() <= 1


def test_audit_contains_keys_only():
    a = pd.read_csv(OUT / "privacy_suppression_audit.csv")
    assert set(a.columns) == {"department", "job_level", "gender", "reason"}
    m = _masked()
    assert len(a) == int((m["suppression"] != "published").sum())
