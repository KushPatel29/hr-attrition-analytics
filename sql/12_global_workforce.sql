/* ===========================================================================
   12_global_workforce.sql  —  the workforce by market, and the talent grid

   A company-wide headcount and a company-wide attrition rate are averages
   over labour markets that behave nothing like one another. This pulls the
   geography apart:

     workforce_by_country — headcount, attrition, pay position, work model and
                            representation per country, plus each market's
                            share of the whole. The concentration column is
                            the one an operating-model review reads first:
                            where a large share of a capability sits in a
                            single market, that market's attrition is not a
                            local problem.

     nine_box             — the talent review grid: performance against
                            potential for ACTIVE employees only. Nine boxes,
                            with the four that matter named rather than left
                            as coordinates.

   Produces workforce_by_country and nine_box.
   Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS workforce_by_country;
CREATE TABLE workforce_by_country AS
WITH emp AS (
    SELECT
        e.*, j.job_level, j.level_rank, j.is_management,
        l.country, l.region, l.salary_index
    FROM fact_employees e
    JOIN dim_job      j ON e.job_id      = j.job_id
    JOIN dim_location l ON e.location_id = l.location_id
),
agg AS (
    SELECT
        country,
        region,
        COUNT(*)                                                          AS headcount_ever,
        SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END)                    AS headcount,
        SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END)                    AS exits,
        SUM(CASE WHEN is_active = 0 AND term_type = 'Voluntary' THEN 1 ELSE 0 END)
                                                                          AS voluntary_exits,
        SUM(CASE WHEN is_active = 0 AND term_type = 'Voluntary'
                      AND performance_rating >= 4 THEN 1 ELSE 0 END)      AS regretted_exits,
        SUM(CASE WHEN is_active = 1 AND is_management = 1 THEN 1 ELSE 0 END)
                                                                          AS managers,
        SUM(CASE WHEN is_active = 1 AND level_rank >= 6 THEN 1 ELSE 0 END) AS senior_roles,
        SUM(CASE WHEN is_active = 1 AND gender = 'Female' THEN 1 ELSE 0 END)
                                                                          AS women,
        SUM(CASE WHEN is_active = 1 AND gender = 'Female' AND level_rank >= 6
                 THEN 1 ELSE 0 END)                                       AS women_senior,
        SUM(CASE WHEN is_active = 1 AND work_model = 'Remote' THEN 1 ELSE 0 END)
                                                                          AS remote,
        SUM(CASE WHEN is_active = 1 AND work_model = 'Hybrid' THEN 1 ELSE 0 END)
                                                                          AS hybrid,
        ROUND(AVG(CASE WHEN is_active = 1 THEN engagement_score END), 1)   AS avg_engagement,
        ROUND(AVG(CASE WHEN is_active = 1 THEN compa_ratio END), 4)        AS avg_compa_ratio,
        ROUND(AVG(CASE WHEN is_active = 1 THEN tenure_months END), 1)      AS avg_tenure_months,
        ROUND(SUM(CASE WHEN is_active = 1 THEN base_salary ELSE 0 END), 0) AS payroll,
        MAX(salary_index)                                                  AS salary_index
    FROM emp
    GROUP BY country, region
)
SELECT
    country,
    region,
    headcount,
    headcount_ever,
    exits,
    voluntary_exits,
    regretted_exits,
    managers,
    senior_roles,
    women,
    remote,
    hybrid,
    avg_engagement,
    avg_compa_ratio,
    avg_tenure_months,
    payroll,
    salary_index,
    ROUND(1.0 * payroll / NULLIF(headcount, 0), 0)                AS avg_salary,
    ROUND(1.0 * exits           / NULLIF(headcount_ever, 0), 4)   AS attrition_rate,
    ROUND(1.0 * voluntary_exits / NULLIF(exits, 0), 4)            AS voluntary_share,
    ROUND(1.0 * regretted_exits / NULLIF(exits, 0), 4)            AS regretted_share,
    ROUND(1.0 * women           / NULLIF(headcount, 0), 4)        AS women_share,
    ROUND(1.0 * women_senior    / NULLIF(senior_roles, 0), 4)     AS women_senior_share,
    ROUND(1.0 * (remote + hybrid) / NULLIF(headcount, 0), 4)      AS flexible_share,
    ROUND(1.0 * headcount / NULLIF((SELECT SUM(headcount) FROM agg), 0), 4)
                                                                  AS share_of_headcount,
    ROUND(1.0 * payroll   / NULLIF((SELECT SUM(payroll)   FROM agg), 0), 4)
                                                                  AS share_of_payroll
FROM agg
ORDER BY headcount DESC;


/* ---------------------------------------------------------------------------
   The nine-box talent grid. Active employees only: a grid that includes
   leavers is a post-mortem, not a talent review.

   Performance collapses 1-5 into three bands so the grid is 3x3 rather than
   5x3; the bands are named because "3,2" is a coordinate and "Core player" is
   a decision.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS nine_box;
CREATE TABLE nine_box AS
WITH emp AS (
    SELECT
        e.employee_id, e.base_salary, e.engagement_score, e.months_since_promotion,
        e.potential_label,
        CASE
            WHEN e.performance_rating <= 2 THEN 'Low'
            WHEN e.performance_rating =  3 THEN 'Medium'
            ELSE 'High'
        END AS performance_band,
        CASE WHEN e.performance_rating <= 2 THEN 1
             WHEN e.performance_rating =  3 THEN 2
             ELSE 3 END AS performance_rank,
        CASE e.potential_label WHEN 'Low' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
                                        AS potential_rank,
        l.country, l.region, d.department
    FROM fact_employees e
    JOIN dim_location   l ON e.location_id   = l.location_id
    JOIN dim_department d ON e.department_id = d.department_id
    WHERE e.is_active = 1
)
SELECT
    performance_band,
    performance_rank,
    potential_label                                              AS potential_band,
    potential_rank,
    CASE
        WHEN performance_rank = 3 AND potential_rank = 3 THEN 'Future leader'
        WHEN performance_rank = 3 AND potential_rank = 2 THEN 'High performer'
        WHEN performance_rank = 3 AND potential_rank = 1 THEN 'Trusted expert'
        WHEN performance_rank = 2 AND potential_rank = 3 THEN 'Growth bet'
        WHEN performance_rank = 2 AND potential_rank = 2 THEN 'Core player'
        WHEN performance_rank = 2 AND potential_rank = 1 THEN 'Steady contributor'
        WHEN performance_rank = 1 AND potential_rank = 3 THEN 'Misplaced talent'
        WHEN performance_rank = 1 AND potential_rank = 2 THEN 'Inconsistent'
        ELSE 'Underperforming'
    END                                                          AS box_label,
    COUNT(*)                                                     AS employees,
    ROUND(1.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM emp), 0), 4) AS share,
    ROUND(AVG(engagement_score), 1)                              AS avg_engagement,
    ROUND(AVG(months_since_promotion), 1)                        AS avg_months_since_promotion,
    ROUND(SUM(base_salary), 0)                                   AS salary,
    /* The box that a retention plan is actually about: strong people who have
       not moved in two years. */
    SUM(CASE WHEN months_since_promotion >= 24 THEN 1 ELSE 0 END) AS stalled
FROM emp
GROUP BY performance_band, performance_rank, potential_label, potential_rank
ORDER BY performance_rank DESC, potential_rank DESC;


/* ---------------------------------------------------------------------------
   One row of geography headlines, so the report and the README quote the same
   figures. The concentration question an operating-model review asks is not
   "what is our attrition" but "how much of the company sits in the markets
   where attrition is worst".
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS geo_headline;
CREATE TABLE geo_headline AS
WITH base AS (
    SELECT
        SUM(headcount)                                        AS headcount,
        SUM(payroll)                                          AS payroll,
        COUNT(*)                                              AS countries,
        ROUND(1.0 * SUM(exits) / NULLIF(SUM(headcount_ever), 0), 4) AS company_rate
    FROM workforce_by_country
),
ranked AS (
    SELECT w.*, b.company_rate, b.headcount AS total_headcount, b.payroll AS total_payroll
    FROM workforce_by_country w CROSS JOIN base b
)
SELECT
    (SELECT countries FROM base)                              AS countries,
    (SELECT headcount FROM base)                              AS headcount,
    (SELECT payroll   FROM base)                              AS payroll,
    (SELECT company_rate FROM base)                           AS company_attrition_rate,
    /* the biggest single market, and what it costs against what it carries */
    (SELECT country FROM ranked ORDER BY headcount DESC LIMIT 1)  AS largest_market,
    (SELECT ROUND(share_of_headcount, 4) FROM ranked ORDER BY headcount DESC LIMIT 1)
                                                              AS largest_market_headcount_share,
    (SELECT ROUND(share_of_payroll, 4)   FROM ranked ORDER BY headcount DESC LIMIT 1)
                                                              AS largest_market_payroll_share,
    /* the market with the worst attrition among those big enough to matter */
    (SELECT country FROM ranked WHERE headcount >= 100 ORDER BY attrition_rate DESC LIMIT 1)
                                                              AS worst_market,
    (SELECT ROUND(attrition_rate, 4) FROM ranked WHERE headcount >= 100
      ORDER BY attrition_rate DESC LIMIT 1)                   AS worst_market_rate,
    (SELECT ROUND(share_of_headcount, 4) FROM ranked WHERE headcount >= 100
      ORDER BY attrition_rate DESC LIMIT 1)                   AS worst_market_headcount_share,
    /* how much of the company sits above the company rate */
    ROUND(1.0 * (SELECT SUM(headcount) FROM ranked WHERE attrition_rate > company_rate)
              / NULLIF((SELECT headcount FROM base), 0), 4)   AS headcount_in_hot_markets,
    ROUND((SELECT MAX(attrition_rate) FROM ranked WHERE headcount >= 100)
        - (SELECT MIN(attrition_rate) FROM ranked WHERE headcount >= 100), 4)
                                                              AS attrition_spread,
    ROUND((SELECT MAX(salary_index) FROM ranked)
        / NULLIF((SELECT MIN(salary_index) FROM ranked), 0), 2) AS pay_market_multiple
FROM base;
