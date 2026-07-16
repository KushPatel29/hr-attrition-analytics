"""
Synthetic HR intervention log — retention actions taken on at-risk employees.

Generates data/fact_hr_interventions.csv for the intervention-effectiveness
analysis (sql/09). Runs AFTER generate_hr_data.py and reads its output; it
never modifies fact_employees, and it uses its own RNG stream, so every
number in the rest of the pipeline is untouched by this file's existence.

How the effect is planted (read this before quoting the results):
  * The "at-risk" population is defined by observable signals — engagement
    < 60, compa-ratio < 0.85, or 24+ months without promotion. sql/09 uses
    the identical rule; a test asserts the two stay in sync.
  * Among at-risk employees who STAYED, 45% have an intervention on record;
    among at-risk employees who LEFT voluntarily, 25% do. That gap IS the
    planted effect — roughly a 13-point retention lift for the treated
    group — and the SQL analysis exists to demonstrate that the join and
    the comparison recover it.
  * This is a FRAMEWORK demo, not a causal estimate. In real data the
    treated group is hand-picked by HR (selection bias), so a raw
    treated-vs-untreated gap overstates or understates the true effect;
    you'd randomize (uplift test) or at minimum match on risk. The README
    spells this out.

Employees with under ~4 months of runway before their exit (or the snapshot)
get no intervention — there was no time to have one.

Usage:
    python data_generator/generate_interventions.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SEED = 43                      # deliberately its own stream — see docstring
SNAPSHOT = pd.Timestamp("2026-06-30")

# Must match sql/09_intervention_effectiveness.sql exactly (test-enforced).
ENGAGEMENT_LT = 60
COMPA_LT = 0.85
MONTHS_SINCE_PROMO_GT = 24

P_TREATED_STAYED = 0.45
P_TREATED_LEFT = 0.25

TYPES = ["Stay interview", "Out-of-cycle raise", "Development plan",
         "Flexible work arrangement", "Internal transfer"]
TYPE_WEIGHTS = [0.35, 0.20, 0.20, 0.15, 0.10]

MIN_RUNWAY_DAYS = 120          # need time between hire and exit for an action


def at_risk(df: pd.DataFrame) -> pd.Series:
    return ((df["engagement_score"] < ENGAGEMENT_LT)
            | (df["compa_ratio"] < COMPA_LT)
            | (df["months_since_promotion"] > MONTHS_SINCE_PROMO_GT))


def main() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    emp = pd.read_csv(DATA / "fact_employees.csv",
                      parse_dates=["hire_date", "termination_date"])

    pool = emp[at_risk(emp)].copy()
    pool["end_date"] = pool["termination_date"].fillna(SNAPSHOT)
    pool["runway_days"] = (pool["end_date"] - pool["hire_date"]).dt.days
    pool = pool[pool["runway_days"] >= MIN_RUNWAY_DAYS]

    stayed = pool["is_active"] == 1
    p = np.where(stayed, P_TREATED_STAYED, P_TREATED_LEFT)
    treated = pool[rng.random(len(pool)) < p].copy()

    # Intervention lands 1-6 months before the exit (leavers) or 1-18 months
    # before the snapshot (actives), never inside the first 90 days.
    lead_days = np.where(
        treated["is_active"] == 1,
        rng.integers(30, 540, len(treated)),
        rng.integers(30, 180, len(treated)),
    )
    date = treated["end_date"] - pd.to_timedelta(lead_days, unit="D")
    earliest = treated["hire_date"] + pd.Timedelta(days=90)
    treated["intervention_date"] = np.maximum(date, earliest)
    treated["intervention_type"] = rng.choice(TYPES, len(treated), p=TYPE_WEIGHTS)

    out = (treated.sort_values("employee_id")
           .reset_index(drop=True)
           .assign(intervention_id=lambda d: d.index + 1)
           [["intervention_id", "employee_id", "intervention_date",
             "intervention_type"]])
    out["intervention_date"] = out["intervention_date"].dt.date
    out.to_csv(DATA / "fact_hr_interventions.csv", index=False)

    print(f"fact_hr_interventions.csv: {len(out)} interventions "
          f"({int(stayed.sum())} at-risk stayers, {int((~stayed).sum())} at-risk leavers in pool)")
    print(out["intervention_type"].value_counts().to_string())
    return out


if __name__ == "__main__":
    main()
