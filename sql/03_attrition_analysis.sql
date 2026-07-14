/* ===========================================================================
   03_attrition_analysis.sql  —  attrition rate cut every which way

   Produces one tidy table (attrition_by_dimension) that stacks attrition
   metrics across seven business dimensions, so a single Power BI slicer /
   bar chart can pivot between them. Each block is a grouped aggregate with
   conditional COUNTs; a window function adds each category's share of total
   separations for ranking.

     attrition_rate  = terminations / headcount_ever   (cumulative, window)
     voluntary_share = voluntary_terms / terminations

   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS attrition_by_dimension;
CREATE TABLE attrition_by_dimension AS
WITH emp AS (
    SELECT
        e.*,
        d.department,
        d.division,
        j.job_level,
        j.level_rank,
        l.region,
        CASE
            WHEN e.tenure_months < 12  THEN '0. <1 yr'
            WHEN e.tenure_months < 24  THEN '1. 1-2 yr'
            WHEN e.tenure_months < 48  THEN '2. 2-4 yr'
            WHEN e.tenure_months < 72  THEN '3. 4-6 yr'
            ELSE '4. 6+ yr'
        END AS tenure_band
    FROM fact_employees e
    JOIN dim_department d ON e.department_id = d.department_id
    JOIN dim_job        j ON e.job_id        = j.job_id
    JOIN dim_location   l ON e.location_id   = l.location_id
),
/* Unpivot employees to (dimension, category) grain, then aggregate once. */
agg AS (
    SELECT dimension, category, MIN(sort_key) AS sort_key,
           COUNT(*)                                            AS headcount_ever,
           SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END)      AS active_headcount,
           SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)      AS terminations,
           SUM(CASE WHEN term_type = 'Voluntary' THEN 1 ELSE 0 END) AS voluntary_terms
    FROM (
        SELECT 'Department' AS dimension, department AS category, department AS sort_key, is_active, term_type FROM emp
        UNION ALL SELECT 'Division', division, division, is_active, term_type FROM emp
        UNION ALL SELECT 'Job Level', job_level, printf('%02d', level_rank), is_active, term_type FROM emp
        UNION ALL SELECT 'Region', region, region, is_active, term_type FROM emp
        UNION ALL SELECT 'Gender', gender, gender, is_active, term_type FROM emp
        UNION ALL SELECT 'Age Band', age_band, age_band, is_active, term_type FROM emp
        UNION ALL SELECT 'Tenure Band', tenure_band, tenure_band, is_active, term_type FROM emp
    )
    GROUP BY dimension, category
)
SELECT
    dimension,
    category,
    sort_key,
    headcount_ever,
    active_headcount,
    terminations,
    voluntary_terms,
    ROUND(1.0 * terminations / NULLIF(headcount_ever, 0), 4)                       AS attrition_rate,
    ROUND(1.0 * voluntary_terms / NULLIF(terminations, 0), 4)                      AS voluntary_share,
    ROUND(1.0 * terminations
              / NULLIF(SUM(terminations) OVER (PARTITION BY dimension), 0), 4)     AS pct_of_dimension_exits,
    RANK() OVER (PARTITION BY dimension ORDER BY 1.0 * terminations
              / NULLIF(headcount_ever, 0) DESC)                                    AS attrition_rank
FROM agg
ORDER BY dimension, sort_key;
