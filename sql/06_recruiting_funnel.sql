/* ===========================================================================
   06_recruiting_funnel.sql  —  hiring funnel, source ROI, time-to-fill

   Three outputs from the application log:
     funnel_stages       : Applied -> Screened -> Interviewed -> Offer -> Hired
                           with stage-over-stage conversion (LAG window) and
                           overall pass-through
     recruiting_by_source: per-channel applications, hire rate, offer-accept
                           rate, avg time-to-fill  (NTILE-style ranking)
     recruiting_kpis     : single-row scorecard incl. median time-to-fill
                           (computed with the classic ROW_NUMBER/COUNT median
                           trick, since SQLite lacks PERCENTILE_CONT)

   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS funnel_stages;
CREATE TABLE funnel_stages AS
WITH stage_counts AS (
    SELECT 'Applied'     AS stage, 1 AS stage_order, COUNT(*)                          AS candidates FROM fact_applications
    UNION ALL SELECT 'Screened',    2, SUM(reached_screen)    FROM fact_applications
    UNION ALL SELECT 'Interviewed', 3, SUM(reached_interview) FROM fact_applications
    UNION ALL SELECT 'Offer',       4, SUM(reached_offer)     FROM fact_applications
    UNION ALL SELECT 'Hired',       5, SUM(hired)             FROM fact_applications
)
SELECT
    stage,
    stage_order,
    candidates,
    ROUND(1.0 * candidates
          / NULLIF(LAG(candidates) OVER (ORDER BY stage_order), 0), 4)  AS conversion_from_prev,
    ROUND(1.0 * candidates
          / NULLIF(FIRST_VALUE(candidates) OVER (ORDER BY stage_order), 0), 4) AS overall_conversion
FROM stage_counts
ORDER BY stage_order;

DROP TABLE IF EXISTS recruiting_by_source;
CREATE TABLE recruiting_by_source AS
WITH src AS (
    SELECT
        source,
        COUNT(*)                                                          AS applications,
        SUM(reached_offer)                                               AS offers,
        SUM(hired)                                                       AS hires,
        SUM(CASE WHEN offer_accepted = 1 THEN 1 ELSE 0 END)             AS offers_accepted,
        AVG(CASE WHEN days_to_fill <> '' THEN days_to_fill END)         AS avg_days_to_fill
    FROM fact_applications
    GROUP BY source
)
SELECT
    source,
    applications,
    offers,
    hires,
    ROUND(1.0 * hires / NULLIF(applications, 0), 4)                     AS hire_rate,
    ROUND(1.0 * offers_accepted / NULLIF(offers, 0), 4)                AS offer_accept_rate,
    ROUND(avg_days_to_fill, 1)                                          AS avg_days_to_fill,
    RANK() OVER (ORDER BY 1.0 * hires / NULLIF(applications, 0) DESC)   AS hire_rate_rank
FROM src
ORDER BY hire_rate DESC;

DROP TABLE IF EXISTS recruiting_kpis;
CREATE TABLE recruiting_kpis AS
WITH fills AS (
    SELECT CAST(days_to_fill AS INTEGER) AS days_to_fill
    FROM fact_applications
    WHERE hired = 1 AND days_to_fill <> ''
),
ranked AS (
    SELECT days_to_fill,
           ROW_NUMBER() OVER (ORDER BY days_to_fill) AS rn,
           COUNT(*)     OVER ()                      AS n
    FROM fills
),
median AS (
    SELECT AVG(days_to_fill) AS median_days_to_fill
    FROM ranked
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)   -- middle 1 (odd) or 2 (even) rows
)
SELECT
    (SELECT COUNT(*) FROM fact_applications)                                             AS total_applications,
    (SELECT SUM(hired) FROM fact_applications)                                           AS total_hires,
    ROUND((SELECT 1.0 * SUM(hired) FROM fact_applications)
          / NULLIF((SELECT COUNT(*) FROM fact_applications), 0), 4)                      AS overall_hire_rate,
    ROUND((SELECT 1.0 * SUM(CASE WHEN offer_accepted = 1 THEN 1 ELSE 0 END) FROM fact_applications)
          / NULLIF((SELECT SUM(reached_offer) FROM fact_applications), 0), 4)            AS offer_accept_rate,
    (SELECT ROUND(median_days_to_fill, 1) FROM median)                                  AS median_days_to_fill,
    (SELECT ROUND(AVG(days_to_fill), 1) FROM fills)                                      AS avg_days_to_fill;
