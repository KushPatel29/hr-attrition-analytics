"""
Synthetic HR data generator for the People Analytics — Attrition & Retention
project.

Produces a small HR star schema (dimensions + an employee master fact, a
compensation-benchmark table, and a recruiting-application funnel) for a
fictional ~2,800-person multinational observed as of 2026-06-30, with
14 sites in 8 countries.

The design goals are deliberate:

  * Attrition is NOT random. Each employee's probability of having left is a
    logistic function of real drivers (short tenure, low engagement, being
    paid below market, promotion stagnation, chronic overtime, long commute).
    That gives the SQL a genuine signal to quantify and the ML model in
    `ml/attrition_model.py` something honest to learn (test-enforced AUC gate).

  * A small, controlled gender pay gap is injected at the *raw* level that
    mostly disappears once you control for job level — the realistic finding a
    pay-equity analysis should surface (see sql/05_pay_equity.sql).

  * Pay is set against the LOCAL market, so compa-ratio is comparable across
    countries and raw salary is not. Country mix therefore shows up as a fake
    pay gap in any analysis that forgets to control for it — which is the trap
    a multinational pay-equity review exists to avoid.

  * Attrition carries a manager effect and a local-market effect on top of the
    personal drivers, so the org chart and the geography are analysable rather
    than decorative. The org is built BEFORE the attrition draw; the other way
    round, no query could ever find a manager effect.

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
    # city, region, country, is_remote_hub, salary_index, attrition_lift
    #
    # salary_index is the local market's pay level against the Canadian
    # baseline. It is why compa-ratio, not raw salary, is the only comparable
    # pay measure in this company: a Bengaluru Senior Analyst paid at local
    # median earns a third of a New York one paid at local median, and a
    # dashboard that puts those two numbers side by side says nothing.
    #
    # attrition_lift is the local market's pull on the logit. Competitive
    # delivery-centre markets churn faster than head-office ones at the same
    # engagement and pay position, which is the geographic finding this data
    # exists to let the analysis find.
    ("Vancouver",       "North America", "Canada",         0, 1.00, 0.00),
    ("Calgary",         "North America", "Canada",         0, 0.94, -0.05),
    ("Toronto",         "North America", "Canada",         0, 1.06, 0.05),
    ("Montreal",        "North America", "Canada",         0, 0.92, -0.05),
    ("Remote - Canada", "North America", "Canada",         1, 0.98, 0.10),
    ("New York",        "North America", "United States",  0, 1.42, 0.15),
    ("Austin",          "North America", "United States",  0, 1.24, 0.10),
    ("Guadalajara",     "Latin America", "Mexico",         0, 0.41, 0.35),
    ("London",          "EMEA",          "United Kingdom", 0, 1.18, 0.05),
    ("Berlin",          "EMEA",          "Germany",        0, 1.02, -0.15),
    ("Krakow",          "EMEA",          "Poland",         0, 0.46, 0.30),
    ("Bengaluru",       "APAC",          "India",          0, 0.29, 0.55),
    ("Hyderabad",       "APAC",          "India",          0, 0.27, 0.50),
    ("Singapore",       "APAC",          "Singapore",      0, 0.97, 0.20),
]

# Headcount weight per site. Shaped like a real multinational rather than
# uniformly: head office plus two large delivery centres carry most of the
# roster, which is exactly why a company-wide attrition rate is a mix of two
# very different labour markets.
LOCATION_WEIGHTS = [
    0.09, 0.05, 0.11, 0.05, 0.06,     # Canada
    0.06, 0.05,                        # United States
    0.05,                              # Mexico
    0.06, 0.04, 0.08,                  # EMEA
    0.16, 0.10, 0.04,                  # APAC
]

WORK_MODELS = ["Onsite", "Hybrid", "Remote"]
WORK_MODEL_P = [0.34, 0.48, 0.18]

POTENTIAL_LABELS = {1: "Low", 2: "Medium", 3: "High"}

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
        [{"location_id": i + 1, "city": c, "region": r, "country": co,
          "is_remote": rem, "salary_index": idx, "attrition_lift": lift}
         for i, (c, r, co, rem, idx, lift) in enumerate(REGIONS)]
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


def gen_comp_benchmark(dim_job: pd.DataFrame, dim_loc: pd.DataFrame) -> pd.DataFrame:
    """Market benchmark per level AND country.

    One global benchmark would put every Indian employee far below market and
    every American one far above it, which is a currency conversion, not a pay
    finding. The country's own market is the only benchmark a compa-ratio can
    mean anything against.
    """
    countries = (dim_loc.groupby("country").salary_index.mean().round(3)
                 .sort_values(ascending=False))
    rows = []
    # One row per job_level, not per level_rank. Two titles can share a rank
    # (Senior Analyst and Specialist are both rank 3) and de-duplicating on
    # rank leaves the second one with no benchmark row at all - which an INNER
    # JOIN then silently drops from every pay analysis.
    for _, j in dim_job.iterrows():
        rank = int(j["level_rank"])
        for country, idx in countries.items():
            median = MARKET_MEDIAN[rank] * float(idx)
            rows.append({
                "country": country,
                "job_level": j["job_level"],
                "level_rank": rank,
                "market_p25": round(median * 0.88, -2),
                "market_median": round(median, -2),
                "market_p75": round(median * 1.16, -2),
            })
    return pd.DataFrame(rows).sort_values(["level_rank", "country"]).reset_index(drop=True)

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def gen_fact_employees(dim_dept, dim_job, dim_loc) -> pd.DataFrame:
    """Build the employee master in the order the causality actually runs.

    Attributes first, then the org (who reports to whom), then the manager
    effect, and only then the attrition draw. The original single pass decided
    attrition before anyone had a manager, which made the org structure
    decorative: no amount of SQL can find a manager effect in data where the
    manager was assigned afterwards.
    """
    n = 2800
    dept_ids = dim_dept["department_id"].tolist()
    loc_ids = dim_loc["location_id"].tolist()
    loc_p = np.array(LOCATION_WEIGHTS)
    loc_p = loc_p / loc_p.sum()
    site = dim_loc.set_index("location_id")

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
        salary_index = float(site.loc[loc_id, "salary_index"])

        # Hire date: senior people tend to have joined earlier.
        max_tenure_yrs = min(8.4, 1.0 + rank * 1.05)
        tenure_years_at_hire = np.random.uniform(0.05, max_tenure_yrs)
        hire_date = SNAPSHOT - pd.Timedelta(days=int(tenure_years_at_hire * 365.25))
        if hire_date < HIRE_START:
            hire_date = HIRE_START + pd.Timedelta(days=random.randint(0, 120))

        potential_tenure_months = (SNAPSHOT - hire_date).days / 30.44

        # Compensation is set against the LOCAL market, not a global one, so
        # compa-ratio means the same thing in Bengaluru and New York. The small
        # controlled raw gender gap is applied inside the local market too.
        local_median = MARKET_MEDIAN[rank] * salary_index
        gender_factor = {"Female": -0.030, "Male": 0.012, "Non-binary": -0.010}[gender]
        noise = np.random.normal(0, 0.075)
        salary = local_median * (1.0 + gender_factor + noise)
        salary = float(round(salary / 100.0) * 100)
        compa_ratio = salary / local_median

        performance = int(np.clip(round(np.random.normal(3.2, 0.9)), 1, 5))
        # Potential is correlated with performance but is NOT performance -
        # a 9-box where the two axes agree is a diagonal line and tells a
        # talent review nothing it did not already know.
        potential = int(np.clip(
            round(np.random.normal(1.4 + 0.30 * performance, 0.75)), 1, 3))
        engagement = float(np.clip(np.random.normal(70, 15), 5, 100))
        overtime = float(np.clip(np.random.gamma(2.0, 4.0), 0, 60))
        commute_km = float(np.clip(np.random.gamma(2.0, 9.0), 0, 90))
        remote_hub = int(site.loc[loc_id, "is_remote"]) == 1
        work_model = ("Remote" if remote_hub
                      else str(np.random.choice(WORK_MODELS, p=WORK_MODEL_P)))
        if work_model == "Remote":
            commute_km = 0.0
        elif work_model == "Hybrid":
            commute_km = round(commute_km * 0.55, 1)
        months_since_promo = float(np.clip(
            np.random.gamma(2.2, 7.0), 0, potential_tenure_months))

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
            "base_salary": salary,
            "compa_ratio": round(compa_ratio, 4),
            "performance_rating": performance,
            "potential_rating": potential,
            "potential_label": POTENTIAL_LABELS[potential],
            "engagement_score": round(engagement, 1),
            "overtime_hours": round(overtime, 1),
            "commute_km": round(commute_km, 1),
            "work_model": work_model,
            "months_since_promotion": round(months_since_promo, 1),
            "_rank": rank,
            "_tenure_potential": potential_tenure_months,
            "_attrition_lift": float(site.loc[loc_id, "attrition_lift"]),
        })

    df = pd.DataFrame(rows)

    # --- the org, before anyone has left ---------------------------------
    # A manager must sit at a strictly higher level than their report. That is
    # what makes the reporting graph acyclic, and an org chart with a cycle in
    # it is not an org chart: a recursive walk up the chain never terminates,
    # and every "how many layers deep are we" answer is the loop guard.
    # Preference order is same department and region, then same department,
    # then anyone senior enough - a reporting line that crosses eight time
    # zones is the exception, not the rule.
    region = site["region"].to_dict()
    df["_region"] = df.location_id.map(region)
    mgmt_ids = set(dim_job[dim_job["is_management"] == 1]["job_id"])
    candidates = df[df.job_id.isin(mgmt_ids)]

    by_rank_dept_region, by_rank_dept, by_rank = {}, {}, {}
    for _, c in candidates.iterrows():
        by_rank.setdefault(c._rank, []).append(c.employee_id)
        by_rank_dept.setdefault((c._rank, c.department_id), []).append(c.employee_id)
        by_rank_dept_region.setdefault(
            (c._rank, c.department_id, c._region), []).append(c.employee_id)

    senior_ranks = sorted(by_rank)          # ascending

    def pick_manager(row):
        higher = [r for r in senior_ranks if r > row._rank]
        for r in higher:                    # nearest senior rank first
            for pool in (by_rank_dept_region.get((r, row.department_id, row._region), []),
                         by_rank_dept.get((r, row.department_id), []),
                         by_rank.get(r, [])):
                pool = [m for m in pool if m != row.employee_id]
                if pool:
                    return random.choice(pool)
        return ""                           # the top layer reports to nobody

    df["manager_id"] = df.apply(pick_manager, axis=1)

    # Manager effect: a latent per-manager quality, invisible in the data, that
    # shifts their team's attrition logit. This is the whole reason to build
    # the org before the attrition draw - it makes "attrition clusters under
    # certain managers" a fact the SQL can find rather than an artefact.
    mgr_effect = {m: float(np.random.normal(0, 0.55))
                  for m in candidates.employee_id}
    df["_mgr_effect"] = df.manager_id.map(mgr_effect).fillna(0.0)

    # --- attrition -------------------------------------------------------
    z = np.full(len(df), -2.15)
    z += 0.85 * np.exp(-df._tenure_potential / 14.0)              # early tenure
    z += 0.80 * ((70 - df.engagement_score) / 30.0)               # low engagement
    z += 1.00 * ((0.97 - df.compa_ratio) / 0.15).clip(lower=0)    # underpaid
    z += 0.45 * ((df.months_since_promotion - 24) / 18.0).clip(lower=0)
    z += 0.45 * (df.overtime_hours / 25.0)                        # burnout
    z += 0.22 * (df.commute_km / 45.0)                            # commute
    z += 0.30 * (3.2 - df.performance_rating)                     # low performers
    z += df._attrition_lift                                       # local market
    z += df._mgr_effect                                           # who they report to
    z += np.random.normal(0, 0.50, len(df))                       # irreducible noise
    left = np.random.random(len(df)) < _sigmoid(z)

    term_date, term_type, tenure_months = [], [], []
    # itertuples() mangles the leading-underscore working columns, so read the
    # three series this loop needs directly.
    for i, (hire_s, potential, perf) in enumerate(zip(
            df.hire_date, df._tenure_potential, df.performance_rating)):
        hire = pd.Timestamp(hire_s)
        if not left[i]:
            term_date.append("")
            term_type.append("")
            tenure_months.append(round(potential, 1))
            continue
        frac = np.random.uniform(0.15, 0.98)
        dt = hire + pd.Timedelta(days=int(frac * (SNAPSHOT - hire).days))
        if dt >= SNAPSHOT:
            dt = SNAPSHOT - pd.Timedelta(days=1)
        # Most separations are voluntary; low performers skew involuntary.
        p_invol = float(np.clip(0.22 + 0.12 * (3.2 - perf), 0.05, 0.6))
        term_date.append(dt.date().isoformat())
        term_type.append("Involuntary" if np.random.random() < p_invol else "Voluntary")
        tenure_months.append(round((dt - hire).days / 30.44, 1))

    df["termination_date"] = term_date
    df["term_type"] = term_type
    df["is_active"] = (~left).astype(int)
    df["tenure_months"] = tenure_months

    banded = pd.cut(
        df["tenure_months"],
        bins=[-0.1, 12, 24, 48, 72, 10_000],
        labels=["<1 yr", "1-2 yr", "2-4 yr", "4-6 yr", "6+ yr"],
    )
    df["tenure_band"] = banded.astype(str)
    df["tenure_band_sort"] = banded.cat.codes.astype(int)

    order = ["employee_id", "employee_name", "department_id", "job_id", "location_id",
             "manager_id", "gender", "ethnicity_group", "age_band", "hire_date",
             "termination_date", "term_type", "is_active", "tenure_months",
             "tenure_band", "tenure_band_sort", "base_salary", "compa_ratio",
             "performance_rating", "potential_rating", "potential_label",
             "engagement_score", "overtime_hours", "commute_km", "work_model",
             "months_since_promotion"]
    return df[order]


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
    comp = gen_comp_benchmark(dim_job, dim_loc)
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
