/* ===========================================================================
   08_privacy_masking.sql  —  k-anonymity masking for small segments

   The problem: a dashboard that lets you filter compensation metrics by
   Department x Level x Gender will, somewhere in the grid, produce a segment
   containing one person. Filter to that cell and you are reading an
   individual's salary. The fix is small-cell suppression (k-anonymity):
   metrics for any segment with fewer than K people are never published.

     K = 5  (the threshold most statistical agencies use for workforce
             tables; change it in one place below if policy differs)

   Two rules, because the naive version has a hole:

     1. PRIMARY suppression: a cell with n < K active employees gets NULL
        metrics (avg salary, compa-ratio, engagement) and its headcount is
        banded to '<5' rather than published exactly.

     2. COMPLEMENTARY suppression (the "two-cell rule"): if exactly one cell
        in a department x level group is suppressed, the next-smallest cell
        in that group is suppressed as well. Otherwise the hidden cell is
        recoverable by subtraction — group total (published elsewhere) minus
        the visible cells equals the "protected" one. With two cells hidden,
        subtraction only ever recovers their blend, never an individual.
        Suppressing the *whole* group instead (the blunt version) destroys
        ~70% of this grid, because every Non-binary cell is small — the
        two-cell rule is how real workforce tables stay useful.

   Produces:
     masked_segment_metrics     the publishable segment table (what a
                                dashboard should consume instead of raw cuts)
     privacy_suppression_audit  one row per suppressed cell with the reason —
                                segment keys only, no metrics, so the audit
                                itself leaks nothing

   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS masked_segment_metrics;
CREATE TABLE masked_segment_metrics AS
WITH cells AS (
    SELECT
        d.department,
        j.job_level,
        j.level_rank,
        e.gender,
        COUNT(*)                    AS n_active,
        AVG(e.base_salary)          AS avg_salary,
        AVG(e.compa_ratio)          AS avg_compa_ratio,
        AVG(e.engagement_score)     AS avg_engagement
    FROM fact_employees e
    JOIN dim_department d ON e.department_id = d.department_id
    JOIN dim_job        j ON e.job_id        = j.job_id
    WHERE e.is_active = 1
    GROUP BY d.department, j.job_level, j.level_rank, e.gender
),
flagged AS (
    SELECT
        *,
        CASE WHEN n_active < 5 THEN 1 ELSE 0 END AS is_primary,
        /* how many cells in this dept x level group are primary-suppressed */
        SUM(CASE WHEN n_active < 5 THEN 1 ELSE 0 END)
            OVER (PARTITION BY department, job_level)                AS group_primaries,
        /* rank the surviving (n >= K) cells smallest-first, to pick the
           complementary victim when the two-cell rule requires one */
        ROW_NUMBER() OVER (
            PARTITION BY department, job_level,
                         CASE WHEN n_active < 5 THEN 1 ELSE 0 END
            ORDER BY n_active, gender)                               AS rn_in_class
    FROM cells
),
decided AS (
    SELECT
        *,
        CASE
            WHEN is_primary = 1 THEN 'suppressed: n < 5'
            WHEN group_primaries = 1 AND rn_in_class = 1
                THEN 'suppressed: complementary (two-cell rule)'
            ELSE 'published'
        END AS suppression
    FROM flagged
)
SELECT
    department,
    job_level,
    level_rank,
    gender,
    CASE WHEN suppression <> 'published' AND n_active < 5
         THEN '<5' ELSE CAST(n_active AS TEXT) END                        AS n_band,
    CASE WHEN suppression <> 'published' THEN NULL ELSE ROUND(avg_salary, 0) END      AS avg_salary,
    CASE WHEN suppression <> 'published' THEN NULL ELSE ROUND(avg_compa_ratio, 4) END AS avg_compa_ratio,
    CASE WHEN suppression <> 'published' THEN NULL ELSE ROUND(avg_engagement, 1) END  AS avg_engagement,
    suppression
FROM decided
ORDER BY department, level_rank, gender;

/* Audit trail: which cells were withheld and why. Keys and reason only —
   publishing the suppressed metrics here would defeat the point. */
DROP TABLE IF EXISTS privacy_suppression_audit;
CREATE TABLE privacy_suppression_audit AS
SELECT
    department,
    job_level,
    gender,
    suppression AS reason
FROM masked_segment_metrics
WHERE suppression <> 'published'
ORDER BY department, job_level, gender;
