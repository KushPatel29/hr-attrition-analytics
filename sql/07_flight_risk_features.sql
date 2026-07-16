/* ===========================================================================
   07_flight_risk_features.sql  —  modelling feature view

   One row per employee with the target (left_flag) and the driver features
   the ML model consumes (ml/attrition_model.py). Two features are engineered
   with window functions to give the model relative context, not just absolute
   values:

     engagement_vs_dept : engagement minus the employee's department average
                          (AVG ... OVER PARTITION BY department)
     comp_gap_vs_level  : compa_ratio minus the level's median compa_ratio
                          (how underpaid relative to same-level peers)

   The view also carries the protected attributes (gender, ethnicity_group,
   age_band). They are NOT model inputs — ml/attrition_model.py excludes them
   from its feature list — but the fairness audit (ml/fairness_audit.py) needs
   them to measure selection rates across groups. Auditable but not learnable.

   The model trains on all employees (left_flag known) and scores the currently
   active population. Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS flight_risk_features;
CREATE TABLE flight_risk_features AS
WITH emp AS (
    SELECT
        e.employee_id,
        d.department,
        d.division,
        j.job_level,
        j.level_rank,
        l.region,
        e.gender,
        e.ethnicity_group,
        e.age_band,
        e.is_active,
        CASE WHEN e.is_active = 0 THEN 1 ELSE 0 END AS left_flag,
        e.tenure_months,
        e.compa_ratio,
        e.performance_rating,
        e.engagement_score,
        e.overtime_hours,
        e.commute_km,
        e.months_since_promotion
    FROM fact_employees e
    JOIN dim_department d ON e.department_id = d.department_id
    JOIN dim_job        j ON e.job_id        = j.job_id
    JOIN dim_location   l ON e.location_id   = l.location_id
)
SELECT
    employee_id,
    department,
    division,
    job_level,
    level_rank,
    region,
    gender,
    ethnicity_group,
    age_band,
    is_active,
    left_flag,
    tenure_months,
    compa_ratio,
    performance_rating,
    engagement_score,
    overtime_hours,
    commute_km,
    months_since_promotion,
    ROUND(engagement_score - AVG(engagement_score) OVER (PARTITION BY department), 2) AS engagement_vs_dept,
    ROUND(compa_ratio - AVG(compa_ratio) OVER (PARTITION BY level_rank), 4)           AS comp_gap_vs_level
FROM emp;
