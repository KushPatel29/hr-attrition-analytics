/* ===========================================================================
   05_pay_equity.sql  —  gender pay gap, raw vs level-adjusted

   The headline "women earn X% less" number mixes two things: real
   within-level pay differences, and the fact that men and women are
   distributed differently across levels. This query separates them:

     raw_gap_pct       : (avg male salary − avg female salary) / avg male,
                         computed *within each job level* (already controls
                         for level)
     adjusted_gap_pct  : headcount-weighted average of the within-level gaps
                         = the gap that remains after holding level constant
                         (the 'ALL' summary row)
     female/male_compa : average compa-ratio vs the external market median,
                         so you can see if a level is underpaid overall

   Produces pay_equity (one row per level + an 'ALL' roll-up).
   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS pay_equity;
CREATE TABLE pay_equity AS
WITH emp AS (
    SELECT e.employee_id, e.gender, e.base_salary, e.compa_ratio,
           j.job_level, j.level_rank, b.market_median
    FROM fact_employees e
    JOIN dim_job        j ON e.job_id = j.job_id
    JOIN comp_benchmark b ON j.job_level = b.job_level
    WHERE e.is_active = 1
      AND e.gender IN ('Female', 'Male')   -- non-binary n too small for a stable gap
),
by_level AS (
    SELECT
        job_level,
        level_rank,
        market_median,
        SUM(CASE WHEN gender = 'Female' THEN 1 ELSE 0 END)                                       AS n_female,
        SUM(CASE WHEN gender = 'Male'   THEN 1 ELSE 0 END)                                       AS n_male,
        AVG(CASE WHEN gender = 'Female' THEN base_salary END)                                    AS avg_salary_female,
        AVG(CASE WHEN gender = 'Male'   THEN base_salary END)                                    AS avg_salary_male,
        AVG(CASE WHEN gender = 'Female' THEN compa_ratio END)                                    AS female_compa_ratio,
        AVG(CASE WHEN gender = 'Male'   THEN compa_ratio END)                                    AS male_compa_ratio
    FROM emp
    GROUP BY job_level, level_rank, market_median
),
scored AS (
    SELECT
        job_level,
        level_rank,
        market_median,
        n_female, n_male,
        ROUND(avg_salary_female, 0) AS avg_salary_female,
        ROUND(avg_salary_male, 0)   AS avg_salary_male,
        ROUND(female_compa_ratio, 4) AS female_compa_ratio,
        ROUND(male_compa_ratio, 4)   AS male_compa_ratio,
        ROUND((avg_salary_male - avg_salary_female) / NULLIF(avg_salary_male, 0), 4) AS raw_gap_pct
    FROM by_level
)
SELECT
    job_level, level_rank, market_median,
    n_female, n_male,
    avg_salary_female, avg_salary_male,
    female_compa_ratio, male_compa_ratio,
    raw_gap_pct,
    CASE
        WHEN raw_gap_pct >= 0.05 THEN 'Review: gap >= 5%'
        WHEN raw_gap_pct <= -0.05 THEN 'Review: reverse gap'
        ELSE 'Within tolerance'
    END AS gap_flag
FROM scored

UNION ALL

/* Level-adjusted roll-up: weight each level's gap by its combined headcount. */
SELECT
    'ALL (level-adjusted)' AS job_level, 99 AS level_rank, NULL AS market_median,
    SUM(n_female) AS n_female, SUM(n_male) AS n_male,
    ROUND(SUM(avg_salary_female * n_female) / NULLIF(SUM(n_female), 0), 0) AS avg_salary_female,
    ROUND(SUM(avg_salary_male   * n_male)   / NULLIF(SUM(n_male), 0), 0)   AS avg_salary_male,
    ROUND(SUM(female_compa_ratio * n_female) / NULLIF(SUM(n_female), 0), 4) AS female_compa_ratio,
    ROUND(SUM(male_compa_ratio   * n_male)   / NULLIF(SUM(n_male), 0), 4)   AS male_compa_ratio,
    ROUND(SUM(raw_gap_pct * (n_female + n_male)) / NULLIF(SUM(n_female + n_male), 0), 4) AS raw_gap_pct,
    'Adjusted gap' AS gap_flag
FROM scored
ORDER BY level_rank;

/* Levels only (excludes the ALL roll-up) — convenient for per-level charts. */
DROP TABLE IF EXISTS pay_equity_levels;
CREATE TABLE pay_equity_levels AS
SELECT * FROM pay_equity WHERE job_level <> 'ALL (level-adjusted)';
