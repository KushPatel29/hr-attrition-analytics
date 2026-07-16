"""
Survival analysis — when do people leave, not just whether.

The retention-cohort triangle (sql/04) shows historic drop-off; the flight-risk
model (ml/attrition_model.py) ranks who is likely to leave next. This module
answers the question workforce planners actually ask: "how long does an
employee survive, and what changes the clock?" — with the statistics built
for it:

  * Kaplan-Meier curves with proper CENSORING. An active employee hasn't
    "not left" — their exit simply hasn't happened yet, and treating them as
    survivors-forever biases every naive tenure average. KM handles it.
  * Event = VOLUNTARY termination. Involuntary exits are censored at their
    exit date: a dismissed employee stops being at risk of quitting. (This is
    the standard single-event simplification; a full competing-risks model is
    the production follow-up.)
  * Cox Proportional Hazards for the drivers: hazard ratios per 1 standard
    deviation of each covariate, with confidence intervals and p-values.
    Protected attributes are excluded, same policy as the risk model.

Honesty notes: covariates are last-observed values (engagement at snapshot
for actives, at exit for leavers), not time-varying histories — fine for a
portfolio-scale demo, and the first thing to upgrade with real HRIS event
data. One covariate needed active de-biasing because of exactly this:
raw months_since_promotion is mechanically capped by tenure (someone who
left at month 12 cannot be 30 months past a promotion), so in a naive fit
it comes out "protective" (HR 0.78, p<1e-4) — backwards from the planted
stagnation driver. Normalizing to promo_stagnation_share (months since
promotion as a share of tenure) removes the cap and recovers the real
effect (HR ~2.4, the strongest hazard in the model). Median survival is
reported only if the curve actually crosses 50%; with ~16% voluntary
attrition it doesn't, so the headline is the time to lose 25% of a cohort
(t25) instead of a fabricated "half-life".

Outputs (output/):
    survival_curves.csv       KM coordinates (group_type, group, tenure_months,
                              survival_prob) — plottable directly in Power BI
    survival_medians.csv      per group: n, events, t25, median (if reached)
    cox_hazard_ratios.csv     covariate, HR per +1 SD, 95% CI, p

Figure: docs/survival_curves.png

Usage:
    python ml/survival_analysis.py     (after data generation)
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.utils import qth_survival_times

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"
DOCS = ROOT / "docs"

NAVY, TEAL, ORANGE, PLUM, GREY = "#12436D", "#28A197", "#F46A25", "#801650", "#8A8A8A"

COX_COVARIATES = [
    "compa_ratio", "engagement_score", "overtime_hours",
    "commute_km", "promo_stagnation_share", "performance_rating",
]

ENGAGEMENT_BANDS = [(0, 60, "Engagement < 60"), (60, 75, "Engagement 60-75"),
                    (75, 101, "Engagement 75+")]


def load_population() -> pd.DataFrame:
    emp = pd.read_csv(DATA / "fact_employees.csv")
    dept = pd.read_csv(DATA / "dim_department.csv")
    df = emp.merge(dept, on="department_id")
    df["duration"] = df["tenure_months"]
    # Event of interest: voluntary exit. Actives and involuntary exits are
    # censored at their last observed tenure.
    df["event"] = (df["term_type"] == "Voluntary").astype(int)
    # Share of tenure spent without a promotion. The raw months figure is
    # mechanically capped by tenure and flips sign in a survival model —
    # see the module docstring.
    df["promo_stagnation_share"] = (
        df["months_since_promotion"] / df["tenure_months"].clip(lower=1))
    bands = pd.cut(df["engagement_score"],
                   bins=[b[0] for b in ENGAGEMENT_BANDS] + [ENGAGEMENT_BANDS[-1][1]],
                   labels=[b[2] for b in ENGAGEMENT_BANDS], right=False)
    df["engagement_band"] = bands.astype(str)
    return df


def km_curve(df: pd.DataFrame, label: str) -> tuple[KaplanMeierFitter, pd.DataFrame]:
    kmf = KaplanMeierFitter()
    kmf.fit(df["duration"], df["event"], label=label)
    sf = kmf.survival_function_.reset_index()
    sf.columns = ["tenure_months", "survival_prob"]
    return kmf, sf


def group_summary(df: pd.DataFrame, kmf: KaplanMeierFitter,
                  group_type: str, group: str) -> dict:
    t25 = qth_survival_times(0.75, kmf.survival_function_)
    median = kmf.median_survival_time_
    return {
        "group_type": group_type,
        "group": group,
        "n": len(df),
        "events": int(df["event"].sum()),
        "t25_months": round(float(t25), 1) if np.isfinite(t25) else None,
        "median_months": round(float(median), 1) if np.isfinite(median) else None,
    }


def fit_all(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    curves, medians, fitted = [], [], {}

    kmf, sf = km_curve(df, "All employees")
    fitted["overall"] = kmf
    curves.append(sf.assign(group_type="overall", group="All employees"))
    medians.append(group_summary(df, kmf, "overall", "All employees"))

    for col, group_type in [("engagement_band", "engagement_band"),
                            ("department", "department")]:
        for value, sub in df.groupby(col, observed=True):
            kmf_g, sf_g = km_curve(sub, str(value))
            if col == "engagement_band":
                fitted[str(value)] = kmf_g
            curves.append(sf_g.assign(group_type=group_type, group=str(value)))
            medians.append(group_summary(sub, kmf_g, group_type, str(value)))

    curves_df = pd.concat(curves, ignore_index=True)
    curves_df["survival_prob"] = curves_df["survival_prob"].round(4)
    return curves_df, pd.DataFrame(medians), fitted


def fit_cox(df: pd.DataFrame) -> pd.DataFrame:
    """Cox PH on z-scored covariates so hazard ratios read 'per +1 SD'."""
    cols = COX_COVARIATES
    X = df[cols + ["duration", "event"]].copy()
    for c in cols:
        X[c] = (X[c] - X[c].mean()) / X[c].std()
    cph = CoxPHFitter()
    cph.fit(X, duration_col="duration", event_col="event")
    s = cph.summary
    out = pd.DataFrame({
        "covariate": s.index,
        "hazard_ratio_per_sd": s["exp(coef)"].round(3),
        "hr_ci_low": np.exp(s["coef lower 95%"]).round(3),
        "hr_ci_high": np.exp(s["coef upper 95%"]).round(3),
        "p_value": s["p"].round(6),
    }).reset_index(drop=True)
    return out


def render_figure(fitted: dict, cox: pd.DataFrame) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))

    colors = {"All employees": NAVY, "Engagement < 60": ORANGE,
              "Engagement 60-75": GREY, "Engagement 75+": TEAL}
    for label, kmf in fitted.items():
        name = kmf._label
        kmf.plot_survival_function(ax=ax1, ci_show=(label == "overall"),
                                   color=colors.get(name, GREY), linewidth=2)
    ax1.set_title("Probability of still being employed (Kaplan-Meier)",
                  fontsize=11, fontweight="bold", color=NAVY, loc="left")
    ax1.set_xlabel("Tenure (months)")
    ax1.set_ylabel("Survival probability")
    ax1.set_ylim(0.4, 1.02)
    ax1.legend(fontsize=8, frameon=False)
    ax1.grid(color="#EAEEF3")
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)

    c = cox.sort_values("hazard_ratio_per_sd")
    risky = c["hazard_ratio_per_sd"] > 1
    ax2.barh(c["covariate"], c["hazard_ratio_per_sd"] - 1, left=1,
             color=[ORANGE if r else TEAL for r in risky], alpha=0.85)
    ax2.errorbar(c["hazard_ratio_per_sd"], range(len(c)),
                 xerr=[c["hazard_ratio_per_sd"] - c["hr_ci_low"],
                       c["hr_ci_high"] - c["hazard_ratio_per_sd"]],
                 fmt="none", ecolor=NAVY, elinewidth=1.2, capsize=3)
    ax2.axvline(1, color=NAVY, linewidth=1)
    ax2.set_title("What moves the exit hazard (Cox PH, per +1 SD)",
                  fontsize=11, fontweight="bold", color=NAVY, loc="left")
    ax2.set_xlabel("Hazard ratio  ( <1 protective   |   >1 risky )")
    ax2.grid(color="#EAEEF3", axis="x")
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)

    fig.tight_layout()
    fig.savefig(DOCS / "survival_curves.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> dict:
    df = load_population()
    curves, medians, fitted = fit_all(df)
    cox = fit_cox(df)

    curves.to_csv(OUT / "survival_curves.csv", index=False)
    medians.to_csv(OUT / "survival_medians.csv", index=False)
    cox.to_csv(OUT / "cox_hazard_ratios.csv", index=False)
    render_figure(fitted, cox)

    n_events = int(df["event"].sum())
    print("SURVIVAL ANALYSIS - voluntary attrition")
    print("=" * 60)
    print(f"Population: {len(df):,} employees | events (voluntary exits): "
          f"{n_events} | censored: {len(df) - n_events}")
    eng = medians[medians["group_type"] == "engagement_band"]
    print("\nTime for a cohort to lose 25% of its people (t25):")
    for _, r in eng.iterrows():
        t25 = f"{r['t25_months']:.0f} months" if pd.notna(r["t25_months"]) else "not reached"
        print(f"  {r['group']:<20} {t25}")
    overall = medians[medians["group_type"] == "overall"].iloc[0]
    med = (f"{overall['median_months']:.0f} months"
           if pd.notna(overall["median_months"]) else "not reached in window")
    print(f"\nMedian survival (all): {med}")
    print("\nCox hazard ratios (per +1 SD):")
    for _, r in cox.sort_values("hazard_ratio_per_sd", ascending=False).iterrows():
        print(f"  {r['covariate']:<24} HR={r['hazard_ratio_per_sd']:>6.3f} "
              f"[{r['hr_ci_low']:.3f}, {r['hr_ci_high']:.3f}]  p={r['p_value']:.2g}")
    print("=" * 60)
    return {"curves": curves, "medians": medians, "cox": cox}


if __name__ == "__main__":
    main()
