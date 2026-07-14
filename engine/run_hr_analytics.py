"""
Local HR analytics engine — runs the whole people-analytics mart end-to-end
with no database required, using SQLite as the SQL engine so the analytics
stay in actual SQL (the files in sql/02..07 are executed verbatim, not
re-implemented in pandas).

Flow:
    data/*.csv  ->  in-memory SQLite  ->  execute sql/02..07  ->  output/*.csv

Outputs written to output/ (consumed by the Power BI model and the README
visuals):
    workforce_kpis.csv          monthly headcount, hires, terms, rolling attrition
    headcount_bridge.csv        12-month begin/+hires/-terms/end waterfall
    attrition_by_dimension.csv  attrition rate across 7 business dimensions
    retention_cohorts.csv       hire-cohort survival triangle
    pay_equity.csv              gender pay gap, raw vs level-adjusted
    funnel_stages.csv           recruiting funnel with conversion
    recruiting_by_source.csv    channel ROI
    recruiting_kpis.csv         recruiting scorecard (incl. median time-to-fill)
    flight_risk_features.csv    ML feature view
    summary.txt                 headline numbers

Usage:
    python engine/run_hr_analytics.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SQL = ROOT / "sql"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

SNAPSHOT_DATE = "2026-06-30"

# CSV -> SQLite table name
SOURCE_TABLES = {
    "dim_department": "dim_department.csv",
    "dim_job": "dim_job.csv",
    "dim_location": "dim_location.csv",
    "dim_date": "dim_date.csv",
    "comp_benchmark": "comp_benchmark.csv",
    "fact_employees": "fact_employees.csv",
    "fact_applications": "fact_applications.csv",
}

# SQL scripts executed in order (01 is the T-SQL reference DDL, not run here).
ANALYTICS_SCRIPTS = [
    "02_workforce_kpis.sql",
    "03_attrition_analysis.sql",
    "04_retention_cohorts.sql",
    "05_pay_equity.sql",
    "06_recruiting_funnel.sql",
    "07_flight_risk_features.sql",
]

# Result tables exported to output/
RESULT_TABLES = [
    "workforce_kpis",
    "headcount_bridge",
    "attrition_by_dimension",
    "retention_cohorts",
    "pay_equity",
    "pay_equity_levels",
    "funnel_stages",
    "recruiting_by_source",
    "recruiting_kpis",
    "flight_risk_features",
]


def load_sources(conn: sqlite3.Connection) -> None:
    for table, fname in SOURCE_TABLES.items():
        df = pd.read_csv(DATA / fname, keep_default_na=False, na_values=[])
        df.to_sql(table, conn, index=False, if_exists="replace")
    # Snapshot parameter table referenced by the SQL (SELECT snapshot_date FROM params).
    pd.DataFrame([{"snapshot_date": SNAPSHOT_DATE}]).to_sql(
        "params", conn, index=False, if_exists="replace")


def run_analytics(conn: sqlite3.Connection) -> None:
    for script in ANALYTICS_SCRIPTS:
        sql_text = (SQL / script).read_text(encoding="utf-8")
        conn.executescript(sql_text)


def export_results(conn: sqlite3.Connection) -> dict:
    tables = {}
    for name in RESULT_TABLES:
        df = pd.read_sql(f"SELECT * FROM {name}", conn)
        df.to_csv(OUT / f"{name}.csv", index=False)
        tables[name] = df
    return tables


def write_summary(tables: dict) -> str:
    kpis = tables["workforce_kpis"]
    latest = kpis.iloc[-1]
    pay = tables["pay_equity"]
    adj = pay[pay["job_level"] == "ALL (level-adjusted)"].iloc[0]
    rec = tables["recruiting_kpis"].iloc[0]
    funnel = tables["funnel_stages"]
    hired_conv = funnel[funnel["stage"] == "Hired"]["overall_conversion"].iloc[0]

    lines = [
        "HR ATTRITION & RETENTION - HEADLINE METRICS",
        "=" * 52,
        f"Snapshot date              : {SNAPSHOT_DATE}",
        f"Active headcount           : {int(latest['headcount']):>8,}",
        f"Trailing-12m attrition     : {latest['rolling_12m_attrition_rate']:>8.1%}",
        f"Trailing-12m terminations  : {int(latest['rolling_12m_terms']):>8,}",
        "-" * 52,
        f"Adjusted gender pay gap     : {adj['raw_gap_pct']:>8.1%}  (level-weighted)",
        f"  female avg salary         : ${adj['avg_salary_female']:>10,.0f}",
        f"  male   avg salary         : ${adj['avg_salary_male']:>10,.0f}",
        "-" * 52,
        f"Applications                : {int(rec['total_applications']):>8,}",
        f"Applied -> Hired conversion : {hired_conv:>8.1%}",
        f"Offer accept rate           : {rec['offer_accept_rate']:>8.1%}",
        f"Median time-to-fill (days)  : {rec['median_days_to_fill']:>8.0f}",
        "=" * 52,
    ]
    report = "\n".join(lines)
    (OUT / "summary.txt").write_text(report, encoding="utf-8")
    return report


def main() -> dict:
    conn = sqlite3.connect(":memory:")
    load_sources(conn)
    run_analytics(conn)
    tables = export_results(conn)
    conn.close()

    report = write_summary(tables)
    print(report)
    print(f"\nOutputs written to {OUT}/ - point Power BI at data/ and output/ CSVs.")
    return tables


if __name__ == "__main__":
    main()
