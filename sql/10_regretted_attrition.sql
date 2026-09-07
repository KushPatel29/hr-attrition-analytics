/* ===========================================================================
   10_regretted_attrition.sql  —  which leavers you actually wanted to keep

   An attrition rate treats every departure as the same event. It is not. A
   low performer managed out and a high performer resigning are opposite
   outcomes reported as one number, and a company can cut its headline
   attrition by getting worse at both.

   The split used here is the standard one, stated explicitly so it can be
   argued with rather than assumed:

     regretted      = VOLUNTARY departure of someone rated 4 or 5
     non-regretted  = involuntary, or voluntary at a rating of 1-2
     neutral        = voluntary at a rating of 3 — the middle, counted on its
                      own rather than silently folded into either side

   Two more cuts that a headline rate hides:

     first-year attrition — leaving inside 12 months is a hiring or onboarding
                            failure, not a retention one, and it has a
                            different owner
     salary at risk       — the annual base salary walking out of the door.
                            Base salary, not a replacement-cost multiple:
                            there is no recruiting-cost or productivity-ramp
                            data here, and inventing a multiplier would turn a
                            measurement into an opinion.

   Produces regretted_attrition (by country, department and level) and
   attrition_headline (one row of company-wide figures).
   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS regretted_attrition;
CREATE TABLE regretted_attrition AS
WITH emp AS (
    SELECT
        e.employee_id, e.is_active, e.term_type, e.tenure_months,
        e.performance_rating, e.potential_label, e.base_salary,
        d.department, d.division, j.job_level, j.level_rank, j.is_management,
        l.country, l.region,
        CASE
            WHEN e.is_active = 1                     THEN 'Active'
            WHEN e.term_type = 'Involuntary'         THEN 'Non-regretted'
            WHEN e.performance_rating >= 4           THEN 'Regretted'
            WHEN e.performance_rating <= 2           THEN 'Non-regretted'
            ELSE 'Neutral'
        END AS exit_class
    FROM fact_employees e
    JOIN dim_department d ON e.department_id = d.department_id
    JOIN dim_job        j ON e.job_id        = j.job_id
    JOIN dim_location   l ON e.location_id   = l.location_id
),
agg AS (
    SELECT dimension, category, MIN(sort_key) AS sort_key,
        COUNT(*)                                                        AS headcount_ever,
        SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)                  AS exits,
        SUM(CASE WHEN exit_class = 'Regretted' THEN 1 ELSE 0 END)       AS regretted_exits,
        SUM(CASE WHEN exit_class = 'Non-regretted' THEN 1 ELSE 0 END)   AS non_regretted_exits,
        SUM(CASE WHEN exit_class = 'Neutral' THEN 1 ELSE 0 END)         AS neutral_exits,
        SUM(CASE WHEN is_active = 0 AND tenure_months < 12 THEN 1 ELSE 0 END)
                                                                        AS first_year_exits,
        SUM(CASE WHEN exit_class = 'Regretted' THEN base_salary ELSE 0 END)
                                                                        AS regretted_salary
    FROM (
        SELECT 'Country' AS dimension, country AS category, country AS sort_key,
               is_active, exit_class, tenure_months, base_salary FROM emp
        UNION ALL SELECT 'Region', region, region, is_active, exit_class, tenure_months, base_salary FROM emp
        UNION ALL SELECT 'Department', department, department, is_active, exit_class, tenure_months, base_salary FROM emp
        UNION ALL SELECT 'Division', division, division, is_active, exit_class, tenure_months, base_salary FROM emp
        UNION ALL SELECT 'Job Level', job_level, printf('%02d', level_rank), is_active, exit_class, tenure_months, base_salary FROM emp
    )
    GROUP BY dimension, category
)
SELECT
    dimension,
    category,
    sort_key,
    headcount_ever,
    exits,
    regretted_exits,
    non_regretted_exits,
    neutral_exits,
    first_year_exits,
    ROUND(regretted_salary, 0)                                              AS regretted_salary,
    ROUND(1.0 * exits           / NULLIF(headcount_ever, 0), 4)             AS attrition_rate,
    ROUND(1.0 * regretted_exits / NULLIF(headcount_ever, 0), 4)             AS regretted_rate,
    /* The share of departures that hurt. A falling headline rate with a
       rising regretted share is a worse company, not a better one. */
    ROUND(1.0 * regretted_exits / NULLIF(exits, 0), 4)                      AS regretted_share,
    ROUND(1.0 * first_year_exits / NULLIF(exits, 0), 4)                     AS first_year_share
FROM agg
ORDER BY dimension, sort_key;


/* ---------------------------------------------------------------------------
   Departments only.

   regretted_attrition stacks five dimensions into one tidy table so a single
   slicer can pivot between them. That shape is wrong for a chart with a fixed
   question: plotting `category` without pinning `dimension` puts departments,
   countries and regions on the same axis and adds them together. A chart whose
   title names one dimension reads from a table that only has that one.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS regretted_by_department;
CREATE TABLE regretted_by_department AS
SELECT
    d.department,
    d.division,
    COUNT(*)                                                         AS headcount_ever,
    SUM(CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END)                 AS exits,
    SUM(CASE WHEN e.is_active = 0 AND e.term_type = 'Voluntary'
                  AND e.performance_rating >= 4 THEN 1 ELSE 0 END)   AS regretted_exits,
    SUM(CASE WHEN e.is_active = 0 AND e.tenure_months < 12
             THEN 1 ELSE 0 END)                                      AS first_year_exits,
    ROUND(SUM(CASE WHEN e.is_active = 0 AND e.term_type = 'Voluntary'
                        AND e.performance_rating >= 4
                   THEN e.base_salary ELSE 0 END), 0)                AS regretted_salary,
    ROUND(1.0 * SUM(CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 4)                              AS attrition_rate,
    ROUND(1.0 * SUM(CASE WHEN e.is_active = 0 AND e.term_type = 'Voluntary'
                              AND e.performance_rating >= 4 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 4)                              AS regretted_rate,
    ROUND(1.0 * SUM(CASE WHEN e.is_active = 0 AND e.term_type = 'Voluntary'
                              AND e.performance_rating >= 4 THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END), 0), 4)
                                                                     AS regretted_share
FROM fact_employees e
JOIN dim_department d ON e.department_id = d.department_id
GROUP BY d.department, d.division
ORDER BY regretted_exits DESC;


/* ---------------------------------------------------------------------------
   Company-wide headline, one row, so the report and the README quote the same
   figures rather than each recomputing them.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS attrition_headline;
CREATE TABLE attrition_headline AS
WITH emp AS (
    SELECT
        e.is_active, e.term_type, e.tenure_months, e.performance_rating,
        e.base_salary, e.engagement_score, e.months_since_promotion,
        CASE
            WHEN e.is_active = 1             THEN 'Active'
            WHEN e.term_type = 'Involuntary' THEN 'Non-regretted'
            WHEN e.performance_rating >= 4   THEN 'Regretted'
            WHEN e.performance_rating <= 2   THEN 'Non-regretted'
            ELSE 'Neutral'
        END AS exit_class
    FROM fact_employees e
)
SELECT
    COUNT(*)                                                          AS headcount_ever,
    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END)                    AS active_headcount,
    SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)                    AS exits,
    SUM(CASE WHEN exit_class = 'Regretted' THEN 1 ELSE 0 END)         AS regretted_exits,
    SUM(CASE WHEN exit_class = 'Non-regretted' THEN 1 ELSE 0 END)     AS non_regretted_exits,
    SUM(CASE WHEN exit_class = 'Neutral' THEN 1 ELSE 0 END)           AS neutral_exits,
    SUM(CASE WHEN is_active = 0 AND tenure_months < 12 THEN 1 ELSE 0 END) AS first_year_exits,
    ROUND(SUM(CASE WHEN exit_class = 'Regretted' THEN base_salary ELSE 0 END), 0)
                                                                      AS regretted_salary,
    ROUND(1.0 * SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 4)                               AS attrition_rate,
    ROUND(1.0 * SUM(CASE WHEN exit_class = 'Regretted' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END), 0), 4)
                                                                      AS regretted_share,
    ROUND(1.0 * SUM(CASE WHEN is_active = 0 AND tenure_months < 12 THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END), 0), 4)
                                                                      AS first_year_share,
    /* Exposure among the people still here: high performers who have gone a
       long time without a move. Promotion stagnation is one of the model's
       real drivers, so this is the population the retention budget is for. */
    SUM(CASE WHEN is_active = 1 AND performance_rating >= 4
                  AND months_since_promotion >= 24 THEN 1 ELSE 0 END)  AS stalled_high_performers,
    ROUND(SUM(CASE WHEN is_active = 1 AND performance_rating >= 4
                        AND months_since_promotion >= 24 THEN base_salary ELSE 0 END), 0)
                                                                      AS stalled_salary
FROM emp;
