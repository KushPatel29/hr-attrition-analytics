/* ===========================================================================
   11_org_design.sql  —  span of control, layers, and the manager effect

   Three questions an operating model review asks that no attrition rate can
   answer:

     1. How wide is each manager's span? Too narrow and the layer exists to
        manage one or two people; too wide and nobody is being managed at all.
        The bands used here (< 4 thin, 4-10 healthy, > 10 wide) are the
        conventional ones and are stated in one place so they can be argued
        with.

     2. How many management layers deep is the org? Counted by walking the
        actual reporting chain, not by assuming job level equals layer -
        a Director reporting to a Director is two layers, however the titles
        read.

     3. Does attrition cluster under particular managers? This is the question
        the manager effect exists for, and it only has an answer because the
        org is built before the attrition draw in the generator. Managers with
        at least MIN_TEAM reports are compared to the company rate; anything
        smaller is noise being read as signal.

   Produces span_of_control (per manager), org_layers (per layer) and
   manager_outliers (teams whose attrition is far from the company rate).
   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS span_of_control;
CREATE TABLE span_of_control AS
WITH reports AS (
    SELECT
        e.manager_id                                          AS manager_id,
        COUNT(*)                                              AS reports_total,
        SUM(CASE WHEN e.is_active = 1 THEN 1 ELSE 0 END)      AS reports_active,
        SUM(CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END)      AS reports_exited,
        SUM(CASE WHEN e.is_active = 0 AND e.term_type = 'Voluntary'
                 THEN 1 ELSE 0 END)                           AS reports_voluntary,
        ROUND(AVG(e.engagement_score), 1)                     AS avg_engagement,
        ROUND(AVG(e.compa_ratio), 4)                          AS avg_compa_ratio
    FROM fact_employees e
    WHERE e.manager_id IS NOT NULL AND e.manager_id <> ''
    GROUP BY e.manager_id
)
SELECT
    m.employee_id                                             AS manager_id,
    d.department,
    d.division,
    j.job_level,
    j.level_rank,
    l.country,
    l.region,
    m.is_active                                               AS manager_active,
    r.reports_total,
    r.reports_active,
    r.reports_exited,
    r.reports_voluntary,
    r.avg_engagement,
    r.avg_compa_ratio,
    ROUND(1.0 * r.reports_exited / NULLIF(r.reports_total, 0), 4) AS team_attrition_rate,
    CASE
        WHEN r.reports_active < 4  THEN '1. Thin (<4)'
        WHEN r.reports_active <= 10 THEN '2. Healthy (4-10)'
        ELSE '3. Wide (>10)'
    END                                                        AS span_band
FROM reports r
JOIN fact_employees m ON m.employee_id  = r.manager_id
JOIN dim_department d ON m.department_id = d.department_id
JOIN dim_job        j ON m.job_id        = j.job_id
JOIN dim_location   l ON m.location_id   = l.location_id
ORDER BY r.reports_total DESC;


/* ---------------------------------------------------------------------------
   Layers: walk the reporting chain upward from every employee and count the
   depth. A recursive CTE rather than a level_rank lookup, because titles and
   layers are not the same thing and the gap between them is itself a finding.

   Depth 1 is the top of the house - people with no manager. Everyone is
   counted: dropping the top layer because it has no parent row is how a
   headcount reconciliation quietly loses its executives.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS org_layers;
CREATE TABLE org_layers AS
WITH RECURSIVE actives AS (
    SELECT employee_id, manager_id FROM fact_employees WHERE is_active = 1
),
chain(employee_id, current_id, depth) AS (
    SELECT employee_id, manager_id, 1 FROM actives

    UNION ALL

    SELECT c.employee_id, e.manager_id, c.depth + 1
    FROM chain c
    JOIN fact_employees e ON e.employee_id = c.current_id
    WHERE c.current_id IS NOT NULL AND c.current_id <> ''
      AND c.depth < 12                    -- guard: a cycle would loop forever
),
depth_per_employee AS (
    SELECT employee_id, MAX(depth) AS depth
    FROM chain
    GROUP BY employee_id
)
SELECT
    dp.depth                                                  AS layer,
    COUNT(*)                                                  AS employees,
    ROUND(AVG(e.compa_ratio), 4)                              AS avg_compa_ratio,
    ROUND(AVG(e.engagement_score), 1)                         AS avg_engagement,
    ROUND(AVG(e.base_salary), 0)                              AS avg_salary,
    SUM(CASE WHEN j.is_management = 1 THEN 1 ELSE 0 END)      AS managers,
    ROUND(1.0 * COUNT(*)
              / (SELECT COUNT(*) FROM depth_per_employee), 4) AS share_of_headcount
FROM depth_per_employee dp
JOIN fact_employees e ON e.employee_id = dp.employee_id
JOIN dim_job        j ON e.job_id      = j.job_id
GROUP BY dp.depth
ORDER BY layer;


/* ---------------------------------------------------------------------------
   Manager outliers.

   A team's attrition is only meaningful against a base rate, a minimum team
   size, and the right base rate. The company rate is the WRONG one: managers
   are recruited locally, so a team in a market that churns at 29% and a team
   in one that churns at 12% are not comparable, and ranking them together
   produces a list of countries wearing managers' names. Each team is compared
   to its own country instead.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS manager_outliers;
CREATE TABLE manager_outliers AS
WITH country_rate AS (
    SELECT l.country,
           ROUND(1.0 * SUM(CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 4) AS market_rate
    FROM fact_employees e
    JOIN dim_location l ON e.location_id = l.location_id
    GROUP BY l.country
),
company AS (
    SELECT ROUND(1.0 * SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 4) AS company_rate
    FROM fact_employees
)
SELECT
    s.manager_id,
    s.department,
    s.division,
    s.country,
    s.region,
    s.job_level,
    s.reports_total,
    s.reports_active,
    s.reports_exited,
    s.avg_engagement,
    s.team_attrition_rate,
    c.market_rate,
    co.company_rate,
    ROUND(s.team_attrition_rate - c.market_rate, 4)           AS gap_to_market,
    ROUND(s.team_attrition_rate - co.company_rate, 4)         AS gap_to_company,
    CASE
        WHEN s.team_attrition_rate >= c.market_rate * 1.5 THEN 'Well above market'
        WHEN s.team_attrition_rate <= c.market_rate * 0.5 THEN 'Well below market'
        ELSE 'In line'
    END                                                        AS verdict
FROM span_of_control s
JOIN country_rate c ON c.country = s.country
CROSS JOIN company co
WHERE s.reports_total >= 8            -- MIN_TEAM: below this the rate is noise
ORDER BY gap_to_market DESC;
