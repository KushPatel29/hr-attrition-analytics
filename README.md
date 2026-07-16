# HR People Analytics — Attrition & Retention

[![CI](https://github.com/KushPatel29/hr-attrition-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/KushPatel29/hr-attrition-analytics/actions/workflows/ci.yml)
![SQL](https://img.shields.io/badge/SQL-window%20functions%20%2B%20CTEs-CC2927)
![Power BI](https://img.shields.io/badge/Power%20BI-6--page%20dashboard-F2C811?logo=powerbi&logoColor=black)
![Python](https://img.shields.io/badge/Python-scikit--learn%20%2B%20lifelines-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-52%20passing-3B8C6E)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

Every HR leadership meeting circles the same four questions: *who is leaving,
and why? Are we paying people fairly? Is the hiring funnel healthy? Which of
our current employees will quit next?* This project answers all four with a
**SQL-first** people-analytics mart — the analytics are hand-written SQL
(window functions, CTEs, cohort survival, level-adjusted pay gaps) that a
reviewer can read and audit, executed verbatim by a small Python engine, and
surfaced in a **6-page Power BI dashboard** plus an **explainable
flight-risk model**.

But there's a fifth question that people-analytics work has to answer before
any of the others matter: *can this system be trusted with data about
people?* Compensation, gender, ethnicity, a score predicting whether someone
quits — this is the most sensitive data a company holds. So the pipeline also
ships the guardrails: **k-anonymity masking** so no dashboard filter can
corner a single person's salary, a **fairness audit** that breaks the build
on statistically significant disparate impact, **survival analysis** that
treats time honestly instead of averaging over it, and an **intervention
log** that measures whether retention actions actually worked.

Everything is synthetic (Faker, fixed seeds — no real employee data), but the
logic mirrors real workforce-analytics practice. CI re-runs the whole
pipeline and all 52 tests on every push.

## Headline findings (from the generated snapshot, 2026-06-30)

| Metric | Value |
|--------|-------|
| Active headcount | **1,483** |
| Trailing-12-month attrition | **19.4%** (73% voluntary) |
| Level-adjusted gender pay gap | **3.3%** — small but present in **all 8 levels** |
| Applied → Hired conversion | **8.8%** · median time-to-fill **48 days** |
| Flight-risk model | ROC-AUC **0.738**, top-decile lift **2.4×** — with zero protected attributes |
| Strongest exit hazard (Cox) | promotion stagnation, **HR 2.4 per +1 SD** |
| Low-engagement cohorts | lose 25% of their people by **month 33** (engaged cohorts: never in-window) |
| Retention interventions | **+12.1 pts** retention among treated at-risk employees (planted effect — see caveat) |

The full write-up with the "so what" behind each number is in
[`docs/INSIGHTS.md`](docs/INSIGHTS.md).

## Why SQL-first

The heart of this project is [`sql/`](sql/) — eight analytics files that do
the real work, written to run **as-is on SQLite** (so the repo is runnable by
anyone, no database setup) while reading as clean T-SQL for SQL Server /
Microsoft Fabric. A few of the techniques on show:

- **Point-in-time headcount** reconstructed from hire/termination dates, then a
  windowed trailing-12-month attrition rate
  ([`02_workforce_kpis.sql`](sql/02_workforce_kpis.sql)).
- **Cohort survival** — a retention triangle that correctly handles
  right-censoring by only counting employees who *had the opportunity* to reach
  each tenure milestone ([`04_retention_cohorts.sql`](sql/04_retention_cohorts.sql)).
- **Level-adjusted pay gap** — separating a real within-level pay difference
  from the mix effect of men and women sitting at different levels
  ([`05_pay_equity.sql`](sql/05_pay_equity.sql)).
- **Small-cell suppression** with the two-cell rule, so segment metrics can be
  published without a subtraction attack recovering the hidden cell
  ([`08_privacy_masking.sql`](sql/08_privacy_masking.sql)).

```sql
-- 04_retention_cohorts.sql (excerpts): survival that respects censoring
by_cohort AS (
    SELECT
        CAST(cohort_year AS TEXT) AS cohort_year,
        months_since_hire,
        SUM(CASE WHEN opportunity_months >= months_since_hire THEN 1 ELSE 0 END) AS eligible,
        SUM(CASE WHEN opportunity_months >= months_since_hire
                  AND tenure_months      >= months_since_hire THEN 1 ELSE 0 END) AS retained
    FROM cohort_grid
    GROUP BY cohort_year, months_since_hire
)
...
    /* month-over-month drop within a cohort, via LAG */
    ROUND(1.0 * retained / NULLIF(eligible, 0)
          - LAG(1.0 * retained / NULLIF(eligible, 0))
              OVER (PARTITION BY cohort_year ORDER BY months_since_hire), 4) AS retention_delta
```

The runnable engine [`engine/run_hr_analytics.py`](engine/run_hr_analytics.py)
loads the CSVs into in-memory SQLite, **executes those SQL files verbatim**,
and writes the result tables the dashboard and model consume — so what you read
in `sql/` is exactly what runs.

## The analysis

**Attrition by department** — where the churn actually is:

![Attrition by department](docs/attrition_by_department.png)

**Hire-cohort retention** — the first 18 months are where people leave:

![Retention curve](docs/retention_curve.png)

**Gender pay gap, raw vs level-adjusted** — the honest finding is that a small
gap favoring men shows up in *every* level, so it survives adjustment:

![Pay equity](docs/pay_equity_gap.png)

**12-month headcount bridge** and **recruiting funnel**:

![Headcount bridge](docs/headcount_bridge.png)
![Recruiting funnel](docs/recruiting_funnel.png)

**Survival curves and exit hazards** — engagement bands separate cleanly, and
the Cox model quantifies each driver (details in the next section):

![Survival curves](docs/survival_curves.png)

**What drives flight risk** — the model's own weights (the drivers really do
predict who left):

![Flight risk drivers](docs/flight_risk_drivers.png)

## The flight-risk model

An honest three-way bake-off ([`ml/attrition_model.py`](ml/attrition_model.py))
on a held-out 30% of employees:

| Model | ROC-AUC | PR-AUC | Lift @ top 10% |
|-------|:------:|:-----:|:-----:|
| Baseline (prevalence) | 0.500 | 0.219 | 1.4× |
| **Logistic Regression (shipped)** | **0.738** | 0.452 | **2.4×** |
| Random Forest | 0.731 | 0.476 | 2.7× |

Logistic regression is shipped over the (essentially tied) random forest
because a retention score a business partner has to defend needs **per-employee
reasons**, not a black box — each high-risk employee gets a plain-English driver
(*"early tenure"*, *"paid below level peers"*, *"overdue for promotion"*). A
[pytest gate](tests/test_ml_model.py) fails the build if the shipped model ever
stops beating the baseline or drops below 0.68 AUC.

One design decision worth pausing on: an earlier version of this model
included gender and age band as features, because they were columns and
columns become features if nobody stops them. Removing every protected
attribute moved held-out AUC from 0.736 to **0.738** — that is, the model
never needed to know who people are, only what their situation is. The
fairness audit below exists to verify the same thing holds at the *output*.

## Working with data about people

This is the part of people analytics that doesn't show up in a tutorial, and
it's where this version of the repo went. Four guardrails, each tested in CI.

### 1. A dashboard filter should never corner one person

Filter a comp dashboard to `Finance × Level 8 × Female` and, somewhere in
that grid, you're reading one individual's salary. [`08_privacy_masking.sql`](sql/08_privacy_masking.sql)
applies **k-anonymity (K=5)** to every department × level × gender segment
before it can be published. The subtle part is *complementary suppression*:
hiding only the small cell doesn't work, because group total minus the
visible cells equals the "hidden" one. The blunt fix — suppress the whole
group — destroyed 72% of this grid when I tried it, because every Non-binary
cell is small. The **two-cell rule** used by statistical agencies (always
suppress at least two cells, so subtraction only ever recovers a blend) keeps
97 of 239 cells publishable while making every suppressed cell unrecoverable.
A [suppression audit table](sql/08_privacy_masking.sql) records what was
withheld and why — keys only, no metrics, so the audit itself leaks nothing.

### 2. Bias is a build break, not a slide in a deck

[`ml/fairness_audit.py`](ml/fairness_audit.py) runs after every scoring pass
and checks the **high-risk selection rate** for every gender, ethnicity, and
age group against the reference group — the disparate-impact ratio, screened
with the **four-fifths (80%) rule** from US employment practice. On this data
the screen genuinely fires: the 55+ band comes out at DI 1.33, one ethnicity
group at 0.77. The next step is what separates an audit from an alarm:
EEOC guidance says small-sample disparities need a significance test before
they count, and Fisher's exact test puts both groups at p ≈ 0.23 — noise,
not signal (their underlying attrition base rates are flat). So both land on
a **monitor list** rather than failing the build. A group outside the band
*with* statistical significance exits non-zero and CI goes red; the test
suite proves the gate fires by planting a genuinely biased score and
watching it fail.

### 3. "When do people leave" is a different question from "who"

The retention triangle shows historic drop-off; the risk model ranks people.
[`ml/survival_analysis.py`](ml/survival_analysis.py) answers the planner's
question — how long does a cohort survive — with **Kaplan-Meier curves**
(event = voluntary exit; actives and dismissals are *censored*, not treated
as survivors-forever) and a **Cox proportional-hazards model** for the
drivers. Median survival is never reached at ~16% voluntary attrition, so
the honest headline is **t25**: a cohort with engagement below 60 loses a
quarter of its people by month 33, the 60–75 band by month 42, and the 75+
band not within the observation window at all.

The Cox fit also caught a trap worth telling: raw `months_since_promotion`
came out *protective* (HR 0.78, p < 1e-4) — backwards, and mechanically so,
because someone who left at month 12 can't be 30 months past a promotion.
The covariate was capped by tenure and proxying for survival itself.
Normalizing to *share of tenure without promotion* recovers the real,
planted effect: **HR 2.4 per +1 SD**, the strongest hazard in the model.
Cross-sectional covariates lie to survival models; that's the first thing
to fix with real HRIS event history.

### 4. A risk score nobody acts on is a report, not a system

`data/fact_hr_interventions.csv` is a synthetic log of retention actions
(stay interviews, out-of-cycle raises, development plans) taken on at-risk
employees, and [`09_intervention_effectiveness.sql`](sql/09_intervention_effectiveness.sql)
closes the loop: treated at-risk employees retain at **88.6%** vs **76.5%**
for the untreated — a **+12.1 point** lift, recovered by the SQL with three
choices that each change the answer if skipped (compare within the at-risk
cohort only; exclude dismissals; drop employees who never had the runway to
receive an intervention, or short-tenure quitters stack the control group).

**The caveat, stated plainly:** the effect is *planted by the generator*,
and even on real data this comparison is descriptive, not causal — HR
hand-picks who gets a stay interview, so the treated group is selected, not
randomized. The analysis demonstrates the mechanics of the feedback loop;
a real deployment would randomize interventions or match on risk score. For
the same reason, interventions are deliberately **not** fed back into the
model as features: on synthetic data that's circular (rediscovering your own
planted effect), and on real data an intervention triggered *by* a high
score is leakage wearing a lanyard.

## The dashboard

A 6-page interactive Power BI report, hand-authored as a Power BI Project
(TMDL model + PBIR definition) in [`powerbi/pbip/`](powerbi/pbip/) — open
`HRAttritionAnalytics.pbip` in Power BI Desktop and Refresh
([build guide](powerbi/BUILD_GUIDE.md)). 53 visuals across 6 pages, styled with
the shared Meridian Corporate theme. Screenshots below are the live report
rendered in Power BI Desktop against the pipeline outputs.

**Workforce Scorecard** — KPI cards, attrition gauge vs target, headcount trend,
and a 12-month **waterfall** bridge (begin + hires − terms = end):

![Workforce Scorecard](powerbi/screenshots/01-workforce-scorecard.png)

**Attrition Deep-Dive** — rate by department, voluntary/involuntary **donut**,
exits-by-level **treemap**, rolling-attrition trend, and the early-tenure risk
spike:

![Attrition Deep-Dive](powerbi/screenshots/02-attrition-deep-dive.png)

**Retention & Cohorts** — cohort survival curves and the **retention-triangle
matrix** (each hire-year cohort's % retained at each tenure milestone):

![Retention & Cohorts](powerbi/screenshots/03-retention-cohorts.png)

**Pay Equity** — compa-ratio gauge, salary-by-gender columns, a **scatter**, and
the per-level gap table straight from the SQL:

![Pay Equity](powerbi/screenshots/04-pay-equity.png)

**Recruiting Funnel** — the hiring **funnel**, hire-rate and time-to-fill by
source, and a source scorecard:

![Recruiting Funnel](powerbi/screenshots/05-recruiting-funnel.png)

**Flight Risk (ML)** — high-risk **treemap**, risk-band mix, a tenure ×
engagement **scatter** (the high-risk cluster sits at low tenure / low
engagement), and an actionable **retention watch list** with per-employee
reasons:

![Flight Risk (ML)](powerbi/screenshots/06-flight-risk-ml.png)

## Architecture

```mermaid
flowchart LR
    GEN[generate_hr_data.py] -->|CSV| DATA[(data/ dims + employees)]
    INT[generate_interventions.py] -->|CSV| DATA
    DATA --> ENG[engine/run_hr_analytics.py]
    SQL[sql/02..09 window functions + masking] --> ENG
    ENG -->|CSV| OUT[(output/ analytics)]
    OUT --> ML[ml/attrition_model.py]
    ML -->|risk scores| OUT
    OUT --> FAIR[ml/fairness_audit.py<br/>CI gate]
    DATA --> SURV[ml/survival_analysis.py]
    SURV -->|KM + Cox| OUT
    OUT --> VIZ[analytics/make_visuals.py]
    OUT --> PBI[Power BI 6-page dashboard]
    DATA --> PBI
```

## Repo layout

```
hr-attrition-analytics/
├── data_generator/   generate_hr_data.py (seeded star schema) + generate_interventions.py
├── data/             dimensions + employee master + applications + intervention log (CSV)
├── sql/              01 schema DDL + 02..09 analytics (window functions, CTEs, k-anon masking)
├── engine/           run_hr_analytics.py  (SQLite executes the SQL end-to-end)
├── ml/               attrition_model.py · fairness_audit.py · survival_analysis.py
├── analytics/        make_visuals.py      (README figures)
├── output/           SQL + ML results consumed by Power BI
├── docs/             rendered figures + INSIGHTS.md (findings write-up)
├── powerbi/          pbip/ (TMDL + PBIR), screenshots/, dax_measures.dax, BUILD_GUIDE.md
└── tests/            data / SQL / ML / fairness / privacy / Power BI-integrity invariants
```

## Run it

```bash
pip install -r data_generator/requirements.txt
python data_generator/generate_hr_data.py        # synthetic HR data
python data_generator/generate_interventions.py  # retention-action log
python engine/run_hr_analytics.py                # execute the SQL, write outputs
python ml/attrition_model.py                     # train + score flight risk
python ml/fairness_audit.py                      # disparate-impact gate
python ml/survival_analysis.py                   # Kaplan-Meier + Cox PH
python analytics/make_visuals.py                 # render the figures
pytest tests/ -v                                 # 52 invariants
```

Then open `powerbi/pbip/HRAttritionAnalytics.pbip` in Power BI Desktop.

## Notes and deliberate choices

- **Synthetic data.** Attrition is generated from a latent logistic model of
  real drivers (tenure, engagement, pay-vs-market, promotion stagnation,
  overtime, commute), so the SQL has genuine signal to quantify and the ML
  model has something honest to learn. The intervention effect is likewise
  planted, and labeled as such everywhere it's reported.
- **Demographic fields** (`gender`, `ethnicity_group`, `age_band`) exist to
  demonstrate pay-equity and fairness-audit technique on fictional data. They
  are carried by the feature view for auditing and excluded from every model.
- **k-anonymity, not differential privacy.** Suppression with the two-cell
  rule is the right-sized tool for a 1,900-person internal reporting table
  and is fully verifiable by tests. Differential-privacy noise budgets earn
  their complexity on repeated public releases at much larger scale; adding
  one here would be decoration.
- **No intervention feedback into the model** — see the caveat in section 4
  above. Circular on synthetic data, leakage-prone on real data.
