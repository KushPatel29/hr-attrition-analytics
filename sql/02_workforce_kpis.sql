/* ===========================================================================
   02_workforce_kpis.sql  —  point-in-time headcount + rolling turnover

   Reconstructs a monthly workforce time series from hire/termination dates,
   then uses window functions to derive a trailing-12-month annualized
   attrition rate and a 12-month headcount bridge (begin + hires − terms = end).

   Runs as-is on SQLite (engine). To port to T-SQL / Fabric Warehouse:
     substr(x,1,7)            -> FORMAT(x,'yyyy-MM')
     date(d,'-12 months')     -> DATEADD(MONTH,-12,d)
   =========================================================================== */

DROP TABLE IF EXISTS workforce_kpis;
CREATE TABLE workforce_kpis AS
WITH months AS (
    SELECT month
    FROM dim_date
    WHERE month <= (SELECT substr(snapshot_date, 1, 7) FROM params)
),
monthly AS (
    SELECT
        m.month,
        (SELECT COUNT(*) FROM fact_employees e
           WHERE substr(e.hire_date, 1, 7) <= m.month
             AND (e.termination_date IS NULL OR e.termination_date = ''
                  OR substr(e.termination_date, 1, 7) > m.month)) AS headcount,
        (SELECT COUNT(*) FROM fact_employees e
           WHERE substr(e.hire_date, 1, 7) = m.month)             AS hires,
        (SELECT COUNT(*) FROM fact_employees e
           WHERE substr(e.termination_date, 1, 7) = m.month)      AS terminations,
        (SELECT COUNT(*) FROM fact_employees e
           WHERE substr(e.termination_date, 1, 7) = m.month
             AND e.term_type = 'Voluntary')                       AS voluntary_terms,
        (SELECT COUNT(*) FROM fact_employees e
           WHERE substr(e.termination_date, 1, 7) = m.month
             AND e.term_type = 'Involuntary')                     AS involuntary_terms
    FROM months m
)
SELECT
    month,
    headcount,
    hires,
    terminations,
    voluntary_terms,
    involuntary_terms,
    ROUND(1.0 * terminations / NULLIF(headcount, 0), 4)           AS monthly_turnover_rate,
    SUM(terminations) OVER w                                      AS rolling_12m_terms,
    ROUND(AVG(headcount) OVER w, 1)                               AS rolling_12m_avg_headcount,
    ROUND(1.0 * SUM(terminations) OVER w
               / NULLIF(AVG(headcount) OVER w, 0), 4)             AS rolling_12m_attrition_rate
FROM monthly
WINDOW w AS (ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
ORDER BY month;

/* 12-month headcount bridge for the waterfall visual. Three delta bars whose
   running total (begin + hires - terms) equals the current headcount — the
   waterfall's own Total bar renders that ending headcount. */
DROP TABLE IF EXISTS headcount_bridge;
CREATE TABLE headcount_bridge AS
WITH anchor AS (
    SELECT substr(date((SELECT snapshot_date FROM params), '-12 months'), 1, 7) AS start_month
),
b AS (
    SELECT
        (SELECT headcount FROM workforce_kpis, anchor WHERE month = anchor.start_month)          AS hc_begin,
        (SELECT SUM(hires) FROM workforce_kpis, anchor WHERE month > anchor.start_month)          AS hires_12m,
        (SELECT SUM(terminations) FROM workforce_kpis, anchor WHERE month > anchor.start_month)   AS terms_12m
    FROM anchor
)
SELECT 'Headcount 12mo ago' AS bucket, 1 AS sort_order, hc_begin        AS value FROM b
UNION ALL SELECT '+ Hires',            2, hires_12m                                   FROM b
UNION ALL SELECT '- Terminations',     3, -terms_12m                                  FROM b;
