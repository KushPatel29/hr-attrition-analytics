/* ===========================================================================
   04_retention_cohorts.sql  —  hire-cohort survival (retention triangle)

   For each hire-year cohort and each tenure milestone, computes the share of
   the cohort still employed at that milestone. A "member is retained at month
   m" if their observed tenure reached m; a member only counts in the
   denominator if they had the *opportunity* to reach m (hired at least m
   months before the snapshot) — otherwise the later milestones would be
   artificially depressed by right-censoring.

   Produces:
     retention_cohorts : cohort_year x milestone survival (+ an 'All' cohort
                         pooled row set that drives the overall survival curve)

   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS retention_cohorts;
CREATE TABLE retention_cohorts AS
WITH milestones(months_since_hire) AS (
    VALUES (0), (6), (12), (18), (24), (36), (48), (60)
),
emp AS (
    SELECT
        employee_id,
        CAST(substr(hire_date, 1, 4) AS INTEGER) AS cohort_year,
        tenure_months,
        /* full months of opportunity between hire and snapshot */
        CAST((julianday((SELECT snapshot_date FROM params)) - julianday(hire_date)) / 30.44 AS INTEGER) AS opportunity_months
    FROM fact_employees
),
cohort_grid AS (
    SELECT e.cohort_year, m.months_since_hire, e.tenure_months, e.opportunity_months
    FROM emp e
    CROSS JOIN milestones m
),
by_cohort AS (
    SELECT
        CAST(cohort_year AS TEXT) AS cohort_year,
        cohort_year               AS cohort_sort,
        months_since_hire,
        SUM(CASE WHEN opportunity_months >= months_since_hire THEN 1 ELSE 0 END)                                   AS eligible,
        SUM(CASE WHEN opportunity_months >= months_since_hire AND tenure_months >= months_since_hire THEN 1 ELSE 0 END) AS retained
    FROM cohort_grid
    GROUP BY cohort_year, months_since_hire
),
pooled AS (
    SELECT
        'All' AS cohort_year,
        9999  AS cohort_sort,
        months_since_hire,
        SUM(CASE WHEN opportunity_months >= months_since_hire THEN 1 ELSE 0 END)                                   AS eligible,
        SUM(CASE WHEN opportunity_months >= months_since_hire AND tenure_months >= months_since_hire THEN 1 ELSE 0 END) AS retained
    FROM cohort_grid
    GROUP BY months_since_hire
),
unioned AS (
    SELECT * FROM by_cohort
    UNION ALL
    SELECT * FROM pooled
)
SELECT
    cohort_year,
    cohort_sort,
    months_since_hire,
    eligible,
    retained,
    ROUND(1.0 * retained / NULLIF(eligible, 0), 4) AS retention_rate,
    /* month-over-month drop within a cohort, via LAG */
    ROUND(1.0 * retained / NULLIF(eligible, 0)
          - LAG(1.0 * retained / NULLIF(eligible, 0))
              OVER (PARTITION BY cohort_year ORDER BY months_since_hire), 4) AS retention_delta
FROM unioned
WHERE eligible >= 15          -- suppress thin cohort/milestone cells
ORDER BY cohort_sort, months_since_hire;
