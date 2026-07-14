"""
Render the README figures from the SQL/ML outputs.

Reads only the CSVs in output/ (so the figures always match what the engine
and model produced) and writes PNGs to docs/. Uses the Meridian Corporate
palette shared across the portfolio for a consistent look.

Usage:
    python analytics/make_visuals.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

NAVY = "#12436D"
TEAL = "#28A197"
ORANGE = "#F46A25"
PLUM = "#801650"
GOOD = "#3B8C6E"
BAD = "#C0392B"
NEUTRAL = "#D4A017"
GREY = "#8A8A8A"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#CCCCCC",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": "#EAEEF3",
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "figure.dpi": 120,
})


def _style(ax, title, subtitle=None):
    pad = 30 if subtitle else 12
    ax.set_title(title, fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=pad)
    if subtitle:
        ax.text(0, 1.015, subtitle, transform=ax.transAxes, fontsize=9,
                color=GREY, ha="left", va="bottom")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def headcount_bridge():
    df = pd.read_csv(OUT / "headcount_bridge.csv").sort_values("sort_order")
    labels = df["bucket"].tolist()
    values = df["value"].tolist()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    running = 0
    for i, (lab, val) in enumerate(zip(labels, values)):
        if i == 0 or i == len(labels) - 1:          # absolute begin / end bars
            ax.bar(i, val, color=NAVY, width=0.6)
            ax.text(i, val + 12, f"{val:,.0f}", ha="center", fontsize=9, fontweight="bold")
            running = val
        else:                                        # floating delta bars
            color = GOOD if val >= 0 else BAD
            bottom = running if val >= 0 else running + val
            ax.bar(i, abs(val), bottom=bottom, color=color, width=0.6)
            ax.text(i, bottom + abs(val) + 12, f"{val:+,.0f}", ha="center",
                    fontsize=9, fontweight="bold", color=color)
            running += val
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Employees")
    _style(ax, "12-Month Headcount Bridge",
           "Beginning headcount + hires - terminations = ending headcount")
    fig.tight_layout()
    fig.savefig(DOCS / "headcount_bridge.png", bbox_inches="tight")
    plt.close(fig)


def attrition_by_department():
    df = pd.read_csv(OUT / "attrition_by_dimension.csv")
    d = df[df["dimension"] == "Department"].sort_values("attrition_rate")
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = [BAD if r >= 0.25 else (NEUTRAL if r >= 0.21 else TEAL)
              for r in d["attrition_rate"]]
    ax.barh(d["category"], d["attrition_rate"] * 100, color=colors)
    for y, (r, n) in enumerate(zip(d["attrition_rate"], d["terminations"])):
        ax.text(r * 100 + 0.3, y, f"{r*100:.1f}%  ({int(n)})", va="center", fontsize=8.5)
    ax.set_xlabel("Cumulative separation rate (%)   ·   (n terminations)")
    ax.margins(x=0.14)
    _style(ax, "Attrition by Department",
           "Data & Analytics and Supply Chain run hottest; Customer Support coolest")
    fig.tight_layout()
    fig.savefig(DOCS / "attrition_by_department.png", bbox_inches="tight")
    plt.close(fig)


def retention_curve():
    df = pd.read_csv(OUT / "retention_cohorts.csv")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    cohorts = [c for c in df["cohort_year"].unique() if c != "All"]
    for c in sorted(cohorts):
        sub = df[df["cohort_year"] == c].sort_values("months_since_hire")
        ax.plot(sub["months_since_hire"], sub["retention_rate"] * 100,
                color=GREY, alpha=0.4, linewidth=1)
    allc = df[df["cohort_year"] == "All"].sort_values("months_since_hire")
    ax.plot(allc["months_since_hire"], allc["retention_rate"] * 100,
            color=NAVY, linewidth=2.6, marker="o", label="All cohorts (pooled)")
    for x, y in zip(allc["months_since_hire"], allc["retention_rate"] * 100):
        ax.text(x, y + 1.2, f"{y:.0f}%", ha="center", fontsize=8, color=NAVY)
    ax.set_xlabel("Months since hire")
    ax.set_ylabel("Retention (%)")
    ax.set_ylim(80, 101)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    _style(ax, "Hire-Cohort Retention Curve",
           "Steepest drop is the first 18 months - where onboarding & pay reviews pay off")
    fig.tight_layout()
    fig.savefig(DOCS / "retention_curve.png", bbox_inches="tight")
    plt.close(fig)


def pay_equity_gap():
    df = pd.read_csv(OUT / "pay_equity.csv")
    levels = df[df["job_level"] != "ALL (level-adjusted)"].sort_values("level_rank")
    adj = df[df["job_level"] == "ALL (level-adjusted)"]["raw_gap_pct"].iloc[0]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    colors = [BAD if g >= 0.05 else TEAL for g in levels["raw_gap_pct"]]
    ax.bar(levels["job_level"], levels["raw_gap_pct"] * 100, color=colors)
    ax.axhline(adj * 100, color=NAVY, linestyle="--", linewidth=1.6,
               label=f"Level-adjusted gap: {adj*100:.1f}%")
    ax.axhline(5, color=GREY, linestyle=":", linewidth=1, label="5% review threshold")
    for x, g in enumerate(levels["raw_gap_pct"]):
        ax.text(x, g * 100 + 0.12, f"{g*100:.1f}%", ha="center", fontsize=8)
    ax.set_ylabel("Male - female pay gap, within level (%)")
    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(levels["job_level"], rotation=30, ha="right", fontsize=8.5)
    ax.legend(frameon=False, fontsize=9)
    _style(ax, "Gender Pay Gap - Raw vs Level-Adjusted",
           "A small gap favoring men persists in all 8 levels -> systematic, worth a review")
    fig.tight_layout()
    fig.savefig(DOCS / "pay_equity_gap.png", bbox_inches="tight")
    plt.close(fig)


def recruiting_funnel():
    df = pd.read_csv(OUT / "funnel_stages.csv").sort_values("stage_order")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    palette = [NAVY, "#1E5A86", TEAL, ORANGE, GOOD]
    maxc = df["candidates"].max()
    for i, row in enumerate(df.itertuples()):
        width = row.candidates / maxc
        left = (1 - width) / 2
        ax.barh(len(df) - i, width, left=left, height=0.62, color=palette[i % len(palette)])
        conv = "" if np.isnan(row.conversion_from_prev) else f"  ({row.conversion_from_prev*100:.0f}% of prev)"
        ax.text(0.5, len(df) - i, f"{row.stage}: {row.candidates:,.0f}{conv}",
                ha="center", va="center", color="white", fontsize=9.5, fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_ylim(0.4, len(df) + 0.6)
    ax.axis("off")
    overall = df[df["stage"] == "Hired"]["overall_conversion"].iloc[0]
    _style(ax, "Recruiting Funnel",
           f"Applied -> Hired overall conversion: {overall*100:.1f}%")
    fig.tight_layout()
    fig.savefig(DOCS / "recruiting_funnel.png", bbox_inches="tight")
    plt.close(fig)


def flight_risk_drivers():
    imp = pd.read_csv(OUT / "feature_importance.csv").head(10).iloc[::-1]
    ev = pd.read_csv(OUT / "model_evaluation.csv")
    chosen = ev[ev["is_chosen"] == 1].iloc[0]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    colors = [BAD if w > 0 else TEAL for w in imp["weight"]]
    ax.barh(imp["feature"], imp["weight"], color=colors)
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_xlabel("Standardized weight  (right = raises attrition risk)")
    _style(ax, "What Drives Flight Risk",
           f"{chosen['model']} · held-out ROC-AUC {chosen['roc_auc']:.3f} · "
           f"top-decile lift {chosen['lift_at_decile']:.1f}x")
    fig.tight_layout()
    fig.savefig(DOCS / "flight_risk_drivers.png", bbox_inches="tight")
    plt.close(fig)


def main():
    headcount_bridge()
    attrition_by_department()
    retention_curve()
    pay_equity_gap()
    recruiting_funnel()
    flight_risk_drivers()
    print(f"Wrote 6 figures to {DOCS}/")


if __name__ == "__main__":
    main()
