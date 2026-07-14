"""
Synthetic HR data generator for the People Analytics — Attrition & Retention
project.

Produces a small HR star schema (dimensions + an employee master fact, a
compensation-benchmark table, and a recruiting-application funnel) for a
fictional ~1,900-person company observed as of 2026-06-30.

The design goals are deliberate:

  * Attrition is NOT random. Each employee's probability of having left is a
    logistic function of real drivers (short tenure, low engagement, being
    paid below market, promotion stagnation, chronic overtime, long commute).
    That gives the SQL a genuine signal to quantify and the ML model in
    `ml/attrition_model.py` something honest to learn (test-enforced AUC gate).

  * A small, controlled gender pay gap is injected at the *raw* level that
    mostly disappears once you control for job level — the realistic finding a
    pay-equity analysis should surface (see sql/05_pay_equity.sql).

  * The recruiting funnel has monotonically shrinking stages with
    source-dependent conversion, so funnel math and source ROI are meaningful.

All values are synthetic (Faker + fixed seeds); no real employee data.

Usage:
    python data_generator/generate_hr_data.py
"""

import random
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(29)
np.random.seed(29)
random.seed(29)

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT = pd.Timestamp("2026-06-30")
HIRE_START = pd.Timestamp("2018-01-01")

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    # department, division
    ("Software Engineering", "Technology"),
    ("Data & Analytics", "Technology"),
    ("IT Operations", "Technology"),
    ("Product Management", "Technology"),
    ("Field Sales", "Go-To-Market"),
    ("Inside Sales", "Go-To-Market"),
    ("Marketing", "Go-To-Market"),
    ("Customer Support", "Operations"),
    ("Supply Chain", "Operations"),
    ("Manufacturing", "Operations"),
    ("Finance & Accounting", "Corporate"),
    ("Human Resources", "Corporate"),
]

# job_family -> list of (job_title, job_level, level_rank, is_management)
JOB_LEVELS = [
    ("Associate", 1, 0),
    ("Analyst", 2, 0),
    ("Senior Analyst", 3, 0),
    ("Specialist", 3, 0),
    ("Senior Specialist", 4, 0),
    ("Lead", 5, 0),
    ("Manager", 6, 1),
    ("Senior Manager", 7, 1),
    ("Director", 8, 1),
]

# Market salary anchor by level_rank (used for comp_benchmark + pay logic)
MARKET_MEDIAN = {
    1: 52000, 2: 66000, 3: 82000, 4: 98000,
    5: 118000, 6: 142000, 7: 172000, 8: 210000,
}

REGIONS = [
    # city, region, country, is_remote_hub
    ("Vancouver", "West", "Canada", 0),
    ("Calgary", "West", "Canada", 0),
    ("Toronto", "East", "Canada", 0),
    ("Montreal", "East", "Canada", 0),
    ("Remote - Canada", "Remote", "Canada", 1),
]

GENDERS = ["Female", "Male", "Non-binary"]
GENDER_P = [0.46, 0.51, 0.03]
ETHNIC_GROUPS = ["Group A", "Group B", "Group C", "Group D", "Group E"]
ETHNIC_P = [0.34, 0.22, 0.18, 0.15, 0.11]
AGE_BANDS = ["<25", "25-34", "35-44", "45-54", "55+"]
AGE_P = [0.08, 0.38, 0.31, 0.16, 0.07]

SOURCES = ["Employee Referral", "LinkedIn", "Job Board", "Agency", "Career Site"]
# per-source relative quality: applied->hired multiplier and offer-accept lift
SOURCE_QUALITY = {
    "Employee Referral": 1.55,
    "LinkedIn": 1.10,
    "Job Board": 0.80,
    "Agency": 1.25,
    "Career Site": 0.70,
}


def gen_dim_department() -> pd.DataFrame:
    return pd.DataFrame(
        [{"department_id": i + 1, "department": d, "division": div}
         for i, (d, div) in enumerate(DEPARTMENTS)]
    )


def gen_dim_job() -> pd.DataFrame:
    rows = []
    jid = 1
    for title, rank, is_mgmt in JOB_LEVELS:
        rows.append({
            "job_id": jid,
            "job_title": title,
            "job_level": title,
            "level_rank": rank,
            "is_management": is_mgmt,
        })
        jid += 1
    return pd.DataFrame(rows)


def gen_dim_location() -> pd.DataFrame:
    return pd.DataFrame(
        [{"location_id": i + 1, "city": c, "region": r, "country": co, "is_remote": rem}
         for i, (c, r, co, rem) in enumerate(REGIONS)]
    )


def gen_dim_date() -> pd.DataFrame:
    months = pd.period_range(HIRE_START, SNAPSHOT, freq="M")
    rows = []
    for p in months:
        start = p.to_timestamp()
        rows.append({
            "month": str(p),                       # 'YYYY-MM'
            "month_start": start.date().isoformat(),
            "year": start.year,
            "quarter": f"{start.year}-Q{(start.month - 1) // 3 + 1}",
            "month_num": start.month,
        })
    return pd.DataFrame(rows)


def gen_comp_benchmark(dim_job: pd.DataFrame) -> pd.DataFrame:
    seen = {}
    for _, j in dim_job.iterrows():
        rank = j["level_rank"]
        if rank in seen:
            continue
        median = MARKET_MEDIAN[rank]
        seen[rank] = {
            "job_level": j["job_level"],
            "level_rank": rank,
            "market_p25": round(median * 0.88, -2),
            "market_median": float(median),
            "market_p75": round(median * 1.16, -2),
        }
    return pd.DataFrame(sorted(seen.values(), key=lambda r: r["level_rank"]))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def gen_fact_employees(dim_dept, dim_job, dim_loc) -> pd.DataFrame:
    n = 1900
    dept_ids = dim_dept["department_id"].tolist()
    loc_ids = dim_loc["location_id"].tolist()
    loc_p = np.array([0.30, 0.14, 0.26, 0.12, 0.18])

    # Job level mix skews junior.
    job_rows = dim_job.to_dict("records")
    job_p = np.array([0.16, 0.20, 0.17, 0.12, 0.11, 0.09, 0.08, 0.05, 0.02])
    job_p = job_p / job_p.sum()

    rows = []
    for eid in range(1, n + 1):
        dept_id = random.choice(dept_ids)
        job = np.random.choice(job_rows, p=job_p)
        loc_id = int(np.random.choice(loc_ids, p=loc_p))
        gender = str(np.random.choice(GENDERS, p=GENDER_P))
        ethnicity = str(np.random.choice(ETHNIC_GROUPS, p=ETHNIC_P))
        age_band = str(np.random.choice(AGE_BANDS, p=AGE_P))
        rank = int(job["level_rank"])

        # Hire date: senior people tend to have joined earlier.
        max_tenure_yrs = min(8.4, 1.0 + rank * 1.05)
        tenure_years_at_hire = np.random.uniform(0.05, max_tenure_yrs)
        hire_date = SNAPSHOT - pd.Timedelta(days=int(tenure_years_at_hire * 365.25))
        if hire_date < HIRE_START:
            hire_date = HIRE_START + pd.Timedelta(days=random.randint(0, 120))

        potential_tenure_months = (SNAPSHOT - hire_date).days / 30.44

        # Compensation: market median for level, +/- spread, with a small
        # controlled raw gap by gender that is intentionally modest.
        median = MARKET_MEDIAN[rank]
        gender_factor = {"Female": -0.030, "Male": 0.012, "Non-binary": -0.010}[gender]
        noise = np.random.normal(0, 0.075)
        salary = median * (1.0 + gender_factor + noise)
        salary = float(round(salary / 100.0) * 100)
        compa_ratio = salary / median

        performance = int(np.clip(round(np.random.normal(3.2, 0.9)), 1, 5))
        engagement = float(np.clip(np.random.normal(70, 15), 5, 100))
        overtime = float(np.clip(np.random.gamma(2.0, 4.0), 0, 60))
        commute_km = float(np.clip(np.random.gamma(2.0, 9.0), 0, 90))
        if loc_id == 5:  # remote
            commute_km = 0.0
        months_since_promo = float(np.clip(
            np.random.gamma(2.2, 7.0), 0, potential_tenure_months))

        # --- Latent attrition risk (drivers -> logit) ---
        z = -2.15
        z += 0.85 * np.exp(-potential_tenure_months / 14.0)       # early tenure risk
        z += 0.80 * ((70 - engagement) / 30.0)                    # low engagement
        z += 1.00 * max(0.0, (0.97 - compa_ratio) / 0.15)         # underpaid
        z += 0.45 * max(0.0, (months_since_promo - 24) / 18.0)    # promo stagnation
        z += 0.45 * (overtime / 25.0)                             # burnout
        z += 0.22 * (commute_km / 45.0)                           # commute
        z += 0.30 * (3.2 - performance)                           # low performers pushed
        z += np.random.normal(0, 0.50)                            # irreducible noise
        p_attrit = _sigmoid(z)
        left = np.random.random() < p_attrit

        termination_date = ""
        term_type = ""
        is_active = 1
        tenure_months = round(potential_tenure_months, 1)
        if left:
            # Terminate at some point during their tenure.
            frac = np.random.uniform(0.15, 0.98)
            term_dt = hire_date + pd.Timedelta(days=int(frac * (SNAPSHOT - hire_date).days))
            if term_dt >= SNAPSHOT:
                term_dt = SNAPSHOT - pd.Timedelta(days=1)
            termination_date = term_dt.date().isoformat()
            # Most separations are voluntary; low performers skew involuntary.
            p_invol = 0.22 + 0.12 * (3.2 - performance)
            term_type = "Involuntary" if np.random.random() < np.clip(p_invol, 0.05, 0.6) else "Voluntary"
            is_active = 0
            tenure_months = round((term_dt - hire_date).days / 30.44, 1)

        rows.append({
            "employee_id": eid,
            "employee_name": fake.name(),
            "department_id": dept_id,
            "job_id": int(job["job_id"]),
            "location_id": loc_id,
            "gender": gender,
            "ethnicity_group": ethnicity,
            "age_band": age_band,
            "hire_date": hire_date.date().isoformat(),
            "termination_date": termination_date,
            "term_type": term_type,
            "is_active": is_active,
            "tenure_months": tenure_months,
            "base_salary": salary,
            "compa_ratio": round(compa_ratio, 4),
            "performance_rating": performance,
            "engagement_score": round(engagement, 1),
            "overtime_hours": round(overtime, 1),
            "commute_km": round(commute_km, 1),
            "months_since_promotion": round(months_since_promo, 1),
        })

    df = pd.DataFrame(rows)

    # Assign a manager per employee: a random management-level active employee
    # in the same department (self-referential dimension for span-of-control SQL).
    managers = df[(df["job_id"].isin(dim_job[dim_job["is_management"] == 1]["job_id"]))
                  & (df["is_active"] == 1)]
    mgr_by_dept = {d: g["employee_id"].tolist()
                   for d, g in managers.groupby("department_id")}
    all_mgr = managers["employee_id"].tolist()

    def pick_manager(row):
        pool = [m for m in mgr_by_dept.get(row["department_id"], []) if m != row["employee_id"]]
        if not pool:
            pool = [m for m in all_mgr if m != row["employee_id"]]
        return random.choice(pool) if pool else ""

    df["manager_id"] = df.apply(pick_manager, axis=1)

    # Tenure band (data column so the dashboard can group without extra DAX);
    # tenure_band_sort keeps clean labels while sorting chronologically.
    banded = pd.cut(
        df["tenure_months"],
        bins=[-0.1, 12, 24, 48, 72, 10_000],
        labels=["<1 yr", "1-2 yr", "2-4 yr", "4-6 yr", "6+ yr"],
    )
    df["tenure_band"] = banded.astype(str)
    df["tenure_band_sort"] = banded.cat.codes.astype(int)
    return df


def gen_fact_applications(dim_dept, dim_job) -> pd.DataFrame:
    dept_ids = dim_dept["department_id"].tolist()
    junior_jobs = dim_job[dim_job["level_rank"] <= 5]["job_id"].tolist()
    rows = []
    app_id = 1
    # ~220 requisitions over 2024-2026.
    for req in range(1, 221):
        req_id = f"REQ-{req:04d}"
        dept_id = random.choice(dept_ids)
        job_id = random.choice(junior_jobs)
        n_apps = random.randint(18, 70)
        opened = SNAPSHOT - pd.Timedelta(days=random.randint(30, 720))
        fill_days = int(np.clip(np.random.normal(46, 18), 12, 130))
        for _ in range(n_apps):
            source = str(np.random.choice(SOURCES, p=[0.18, 0.30, 0.24, 0.10, 0.18]))
            q = SOURCE_QUALITY[source]
            applied_date = opened + pd.Timedelta(days=random.randint(0, 25))
            reached_screen = int(np.random.random() < min(0.62 * (0.85 + 0.15 * q), 0.95))
            reached_interview = int(reached_screen and np.random.random() < 0.55 * (0.8 + 0.2 * q))
            reached_offer = int(reached_interview and np.random.random() < 0.34 * (0.75 + 0.25 * q))
            hired = 0
            offer_accepted = ""
            days_to_fill = ""
            if reached_offer:
                accept = np.random.random() < min(0.72 * (0.85 + 0.15 * q), 0.97)
                offer_accepted = 1 if accept else 0
                if accept:
                    hired = 1
                    days_to_fill = fill_days
            rows.append({
                "application_id": app_id,
                "req_id": req_id,
                "department_id": dept_id,
                "job_id": job_id,
                "source": source,
                "applied_date": applied_date.date().isoformat(),
                "reached_screen": reached_screen,
                "reached_interview": reached_interview,
                "reached_offer": reached_offer,
                "hired": hired,
                "offer_accepted": offer_accepted,
                "days_to_fill": days_to_fill,
            })
            app_id += 1
    return pd.DataFrame(rows)


def main() -> None:
    dim_dept = gen_dim_department()
    dim_job = gen_dim_job()
    dim_loc = gen_dim_location()
    dim_date = gen_dim_date()
    comp = gen_comp_benchmark(dim_job)
    employees = gen_fact_employees(dim_dept, dim_job, dim_loc)
    applications = gen_fact_applications(dim_dept, dim_job)

    dim_dept.to_csv(OUT_DIR / "dim_department.csv", index=False)
    dim_job.to_csv(OUT_DIR / "dim_job.csv", index=False)
    dim_loc.to_csv(OUT_DIR / "dim_location.csv", index=False)
    dim_date.to_csv(OUT_DIR / "dim_date.csv", index=False)
    comp.to_csv(OUT_DIR / "comp_benchmark.csv", index=False)
    employees.to_csv(OUT_DIR / "fact_employees.csv", index=False)
    applications.to_csv(OUT_DIR / "fact_applications.csv", index=False)

    active = int(employees["is_active"].sum())
    left = int((employees["is_active"] == 0).sum())
    sep_rate = left / len(employees)
    print("HR synthetic data generated in", OUT_DIR)
    print(f"  employees (ever)   : {len(employees):>6,}")
    print(f"  active headcount   : {active:>6,}")
    print(f"  separations (window): {left:>6,}  ({sep_rate:.1%})")
    print(f"  applications        : {len(applications):>6,}")
    print(f"  requisitions        : {applications['req_id'].nunique():>6,}")


if __name__ == "__main__":
    main()
