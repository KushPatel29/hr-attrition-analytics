/* ===========================================================================
   05_pay_equity.sql  —  gender pay gap: raw, level-adjusted, market-adjusted

   The headline "women earn X% less" number mixes three things in a
   multinational: real within-level pay differences, the fact that men and
   women are distributed differently across levels, and the fact that they are
   distributed differently across COUNTRIES. The third one dominates and is
   the one most reviews forget.

   Pay here is set against the local market, so a Bengaluru Senior Analyst at
   local median and a New York Senior Analyst at local median are both paid
   correctly and their salaries differ by a factor of five. Any gap computed
   on raw salary across countries is therefore measuring the geographic mix of
   the workforce, not its pay decisions. Comparing within (country x level)
   cells is the only comparison that means anything.

     raw_gap_pct         : (avg male − avg female) / avg male within a level,
                           pooled across countries — the contaminated number
     adjusted (ALL)      : headcount-weighted average of the within-level gaps
     market-adjusted     : headcount-weighted average of the within
                           (country x level) gaps — the defensible number
     female/male_compa   : average compa-ratio against the LOCAL market median

   Produces pay_equity (per level + two roll-ups), pay_equity_levels, and
   pay_equity_geo (per country).
   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS pay_equity;
CREATE TABLE pay_equity AS
WITH emp AS (
    SELECT e.employee_id, e.gender, e.base_salary, e.compa_ratio,
           j.job_level, j.level_rank, l.country, b.market_median
    FROM fact_employees e
    JOIN dim_job        j ON e.job_id      = j.job_id
    JOIN dim_location   l ON e.location_id = l.location_id
    /* comp_benchmark is per country AND level; joining on level alone would
       fan every employee out across all eight countries' benchmark rows. */
    JOIN comp_benchmark b ON j.job_level = b.job_level AND l.country = b.country
    WHERE e.is_active = 1
      AND e.gender IN ('Female', 'Male')   -- non-binary n too small for a stable gap
),
by_level AS (
    SELECT
        job_level,
        level_rank,
        AVG(market_median)                                                                       AS market_median,
        SUM(CASE WHEN gender = 'Female' THEN 1 ELSE 0 END)                                       AS n_female,
        SUM(CASE WHEN gender = 'Male'   THEN 1 ELSE 0 END)                                       AS n_male,
        AVG(CASE WHEN gender = 'Female' THEN base_salary END)                                    AS avg_salary_female,
        AVG(CASE WHEN gender = 'Male'   THEN base_salary END)                                    AS avg_salary_male,
        AVG(CASE WHEN gender = 'Female' THEN compa_ratio END)                                    AS female_compa_ratio,
        AVG(CASE WHEN gender = 'Male'   THEN compa_ratio END)                                    AS male_compa_ratio
    FROM emp
    GROUP BY job_level, level_rank
),
scored AS (
    SELECT
        job_level,
        level_rank,
        ROUND(market_median, 0)      AS market_median,
        n_female, n_male,
        ROUND(avg_salary_female, 0)  AS avg_salary_female,
        ROUND(avg_salary_male, 0)    AS avg_salary_male,
        ROUND(female_compa_ratio, 4) AS female_compa_ratio,
        ROUND(male_compa_ratio, 4)   AS male_compa_ratio,
        ROUND((avg_salary_male - avg_salary_female) / NULLIF(avg_salary_male, 0), 4) AS raw_gap_pct
    FROM by_level
),
/* The same comparison one level deeper: inside a single country AND level,
   where two salaries are actually comparable. Cells with no one of a gender
   contribute nothing rather than a spurious 100% gap. */
by_cell AS (
    SELECT
        country, job_level,
        SUM(CASE WHEN gender = 'Female' THEN 1 ELSE 0 END)      AS n_female,
        SUM(CASE WHEN gender = 'Male'   THEN 1 ELSE 0 END)      AS n_male,
        AVG(CASE WHEN gender = 'Female' THEN base_salary END)   AS avg_f,
        AVG(CASE WHEN gender = 'Male'   THEN base_salary END)   AS avg_m,
        AVG(CASE WHEN gender = 'Female' THEN compa_ratio END)   AS compa_f,
        AVG(CASE WHEN gender = 'Male'   THEN compa_ratio END)   AS compa_m
    FROM emp
    GROUP BY country, job_level
    HAVING n_female > 0 AND n_male > 0
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
    'ALL (level-adjusted)' AS job_level, 98 AS level_rank, NULL AS market_median,
    SUM(n_female) AS n_female, SUM(n_male) AS n_male,
    ROUND(SUM(avg_salary_female * n_female) / NULLIF(SUM(n_female), 0), 0) AS avg_salary_female,
    ROUND(SUM(avg_salary_male   * n_male)   / NULLIF(SUM(n_male), 0), 0)   AS avg_salary_male,
    ROUND(SUM(female_compa_ratio * n_female) / NULLIF(SUM(n_female), 0), 4) AS female_compa_ratio,
    ROUND(SUM(male_compa_ratio   * n_male)   / NULLIF(SUM(n_male), 0), 4)   AS male_compa_ratio,
    ROUND(SUM(raw_gap_pct * (n_female + n_male)) / NULLIF(SUM(n_female + n_male), 0), 4) AS raw_gap_pct,
    'Adjusted gap' AS gap_flag
FROM scored

UNION ALL

/* Market-adjusted roll-up: the same weighting inside country x level cells. */
SELECT
    'ALL (level + market-adjusted)' AS job_level, 99 AS level_rank, NULL AS market_median,
    SUM(n_female) AS n_female, SUM(n_male) AS n_male,
    ROUND(SUM(avg_f * n_female) / NULLIF(SUM(n_female), 0), 0) AS avg_salary_female,
    ROUND(SUM(avg_m * n_male)   / NULLIF(SUM(n_male), 0), 0)   AS avg_salary_male,
    ROUND(SUM(compa_f * n_female) / NULLIF(SUM(n_female), 0), 4) AS female_compa_ratio,
    ROUND(SUM(compa_m * n_male)   / NULLIF(SUM(n_male), 0), 4)   AS male_compa_ratio,
    ROUND(SUM(((avg_m - avg_f) / NULLIF(avg_m, 0)) * (n_female + n_male))
              / NULLIF(SUM(n_female + n_male), 0), 4) AS raw_gap_pct,
    'Market-adjusted gap' AS gap_flag
FROM by_cell
ORDER BY level_rank;

/* ---------------------------------------------------------------------------
   Levels only (excludes the roll-ups), with BOTH gaps side by side.

   The pooled within-level gap is the one that misleads in a multinational: a
   "Senior Analyst" in New York and one in Bengaluru are both paid correctly
   for their market and differ by a factor of five, so any gender split that
   happens to sit differently across those markets shows up as a pay gap. The
   market-adjusted column is the same comparison made inside a single country,
   and the difference between the two columns is the geography.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS pay_equity_levels;
CREATE TABLE pay_equity_levels AS
WITH emp AS (
    SELECT e.gender, e.base_salary, j.job_level, l.country
    FROM fact_employees e
    JOIN dim_job      j ON e.job_id      = j.job_id
    JOIN dim_location l ON e.location_id = l.location_id
    WHERE e.is_active = 1 AND e.gender IN ('Female', 'Male')
),
cells AS (
    SELECT country, job_level,
           SUM(CASE WHEN gender = 'Female' THEN 1 ELSE 0 END) AS n_female,
           SUM(CASE WHEN gender = 'Male'   THEN 1 ELSE 0 END) AS n_male,
           AVG(CASE WHEN gender = 'Female' THEN base_salary END) AS avg_f,
           AVG(CASE WHEN gender = 'Male'   THEN base_salary END) AS avg_m
    FROM emp
    GROUP BY country, job_level
    HAVING n_female > 0 AND n_male > 0
),
adjusted AS (
    SELECT job_level,
           SUM(n_female + n_male)                                        AS n_compared,
           COUNT(*)                                                      AS markets_compared,
           ROUND(SUM(((avg_m - avg_f) / NULLIF(avg_m, 0)) * (n_female + n_male))
                     / NULLIF(SUM(n_female + n_male), 0), 4)             AS market_adjusted_gap_pct
    FROM cells
    GROUP BY job_level
)
SELECT p.*,
       a.n_compared,
       a.markets_compared,
       a.market_adjusted_gap_pct,
       ROUND(p.raw_gap_pct - a.market_adjusted_gap_pct, 4) AS gap_explained_by_geography
FROM pay_equity p
LEFT JOIN adjusted a ON a.job_level = p.job_level
WHERE p.level_rank < 98;

/* ---------------------------------------------------------------------------
   Per-country pay position. Two different questions live here and the page
   keeps them apart:
     compa_ratio  — are we paying our people correctly for THEIR market?
     raw salary   — what does that market cost? (a budgeting number, never a
                    fairness one)
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS pay_equity_geo;
CREATE TABLE pay_equity_geo AS
WITH emp AS (
    SELECT e.employee_id, e.gender, e.base_salary, e.compa_ratio,
           j.job_level, j.level_rank, l.country, l.region
    FROM fact_employees e
    JOIN dim_job      j ON e.job_id      = j.job_id
    JOIN dim_location l ON e.location_id = l.location_id
    WHERE e.is_active = 1
),
cells AS (
    SELECT country, region, job_level,
           SUM(CASE WHEN gender = 'Female' THEN 1 ELSE 0 END) AS n_female,
           SUM(CASE WHEN gender = 'Male'   THEN 1 ELSE 0 END) AS n_male,
           AVG(CASE WHEN gender = 'Female' THEN base_salary END) AS avg_f,
           AVG(CASE WHEN gender = 'Male'   THEN base_salary END) AS avg_m
    FROM emp
    WHERE gender IN ('Female', 'Male')
    GROUP BY country, region, job_level
    HAVING n_female > 0 AND n_male > 0
),
totals AS (
    SELECT country, region,
           COUNT(*)                                              AS headcount,
           ROUND(AVG(compa_ratio), 4)                            AS avg_compa_ratio,
           ROUND(AVG(base_salary), 0)                            AS avg_salary,
           ROUND(SUM(base_salary), 0)                            AS payroll,
           ROUND(1.0 * SUM(CASE WHEN compa_ratio < 0.9 THEN 1 ELSE 0 END)
                     / COUNT(*), 4)                              AS below_market_share
    FROM emp
    GROUP BY country, region
)
SELECT
    t.country,
    t.region,
    t.headcount,
    t.avg_compa_ratio,
    t.avg_salary,
    t.payroll,
    t.below_market_share,
    ROUND(SUM(((c.avg_m - c.avg_f) / NULLIF(c.avg_m, 0)) * (c.n_female + c.n_male))
              / NULLIF(SUM(c.n_female + c.n_male), 0), 4) AS market_adjusted_gap_pct
FROM totals t
LEFT JOIN cells c ON c.country = t.country
GROUP BY t.country, t.region, t.headcount, t.avg_compa_ratio,
         t.avg_salary, t.payroll, t.below_market_share
ORDER BY t.headcount DESC;
