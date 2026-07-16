# Findings — what the data actually says

Eight findings a people-analytics team would take to HR leadership, each backed
by a query in [`sql/`](../sql/) or a model in [`ml/`](../ml/). All numbers
come from the committed pipeline outputs (snapshot 2026-06-30) and are
reproducible by re-running the pipeline (see "Run it" in the README).

## 1. Attrition is a department problem, not a company problem

Company-wide trailing-12-month attrition is **19.4%**, but the cumulative
separation rate ranges from **27.5% in Data & Analytics** and **26.6% in
Supply Chain** down to **13.2% in Customer Support** — a 2.1× spread. Retention
budget spent evenly across the company is budget wasted; the hot spots are
two named departments.
*Source: `03_attrition_analysis.sql` → `attrition_by_dimension`.*

## 2. The first year is the cliff

Separation rate by tenure band falls monotonically: **39.4% (<1 yr) → 21.1%
(1–2 yr) → 12.2% (2–4 yr) → 4.6% (4–6 yr) → 1.9% (6+ yr)**. Pooled cohort
survival tells the same story: 95.8% at 6 months, 92.1% at 12, 89.1% at 18 —
then the curve flattens. Onboarding and first-year comp reviews are where
retention interventions pay off; an employee who reaches year two mostly stays.
*Source: `04_retention_cohorts.sql` → `retention_cohorts` (censoring-aware).*

## 3. The pay gap survives the level adjustment — that's the finding

The raw gender pay gap looks small (~3%), and controlling for job level it is
**3.3%**. The tell is the pattern, not the size: the within-level gap favors
men in **all 8 job levels** (0.5%–4.9%). No single level trips the 5% review
threshold, but a gap that shows up everywhere is systematic, not noise — the
kind of result that justifies a comp-review cycle even when every individual
cell is "within tolerance".
*Source: `05_pay_equity.sql` → `pay_equity` (headcount-weighted roll-up).*

## 4. Employee referrals are the best hiring channel — but not the fastest

Referrals convert at a **12.1% applied→hired rate** vs **6.8–7.2%** for job
boards and the career site, with the strongest offer-accept rates alongside
agencies (~79–80%). Nothing beats the ~46–50 day time-to-fill spread by much,
so the channel decision is about conversion quality, not speed: shifting
sourcing mix toward referrals raises funnel yield without lengthening fills.
*Source: `06_recruiting_funnel.sql` → `recruiting_by_source`.*

## 5. Flight risk is predictable enough to act on — and explainable

The shipped logistic model scores held-out employees at **ROC-AUC 0.738** with
a **2.4× lift in the top decile** — i.e., the 10% of employees the model flags
highest contain 2.4× their share of actual leavers. The strongest protective
factor is tenure; the strongest risk factors are being paid below level peers
and below market. Every flagged employee carries a plain-English reason
("paid below level peers", "early tenure", "overdue for promotion"), so the
watch list on the dashboard's Flight Risk page is a to-do list, not a black box.
Notably, the model uses **no protected attributes**: removing gender and age
band from an earlier feature list moved AUC from 0.736 to 0.738 — the
predictive power was never coming from who people are.
*Source: `ml/attrition_model.py` → `model_evaluation`, `feature_importance`,
`flight_risk_scores`.*

## 6. Promotion stagnation is the loudest exit signal — once you un-bias the clock

The Cox proportional-hazards model puts **promotion stagnation at HR 2.4 per
+1 SD** (p < 1e-10), ahead of low engagement (HR 0.76 protective per +1 SD),
overtime (1.15) and pay position (0.89). Getting there required fixing a trap:
raw months-since-promotion looked *protective*, because leavers exit early and
mechanically can't accumulate large values — the covariate was proxying for
tenure. Normalized to *share of tenure without promotion*, the real effect
appears. Kaplan-Meier bands tell the planning story: a cohort with engagement
below 60 loses **25% of its people by month 33**; the 75+ band never loses
that many inside the observation window.
*Source: `ml/survival_analysis.py` → `cox_hazard_ratios`, `survival_medians`.*

## 7. The fairness screen fires — and the follow-up shows why that's not a scandal

The disparate-impact screen (four-fifths rule on high-risk selection rates)
flags the **55+ age band at DI 1.33** and one ethnicity group at 0.77. Fisher's
exact test puts both at **p ≈ 0.23**, and actual attrition base rates are flat
across age bands — these are small-denominator wobbles, not model bias, so both
groups sit on a monitor list rather than blocking the release. The distinction
matters in both directions: a team that ships on the point estimate alone would
be shipping a discrimination finding that isn't there, and a team with no gate
at all would never catch the one that is. A statistically significant violation
fails CI.
*Source: `ml/fairness_audit.py` → `fairness_audit`.*

## 8. Treated at-risk employees retain 12 points better — read the fine print

Within the at-risk cohort (low engagement, below-market pay, or 24+ months
without promotion), employees with a logged retention intervention retain at
**88.6%** vs **76.5%** untreated (**+12.1 pts**, p < 0.001), with development
plans and internal transfers leading. The fine print: this effect is planted
in the synthetic generator, and even on real data a treated-vs-untreated
comparison is descriptive — HR picks who gets a stay interview, so
randomization or risk-score matching is the production follow-up. The value
here is the measurement plumbing: cohort-restricted comparison, dismissals
excluded, and a minimum-runway filter so short-tenure quitters can't stack
the control group.
*Source: `sql/09_intervention_effectiveness.sql` → `intervention_effectiveness`.*
