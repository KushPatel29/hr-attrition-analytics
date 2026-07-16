/* ===========================================================================
   09_intervention_effectiveness.sql  —  did the retention actions work?

   A flight-risk score that managers glance at quarterly is a report; the
   operational loop is score -> act -> measure whether the action moved
   retention. This view closes the loop: it joins the HR intervention log
   (fact_hr_interventions) to subsequent employee outcomes within the
   at-risk cohort.

   Three deliberate choices, each of which changes the answer if skipped:

     1. Cohort = AT-RISK employees only (same rule the intervention program
        targets: engagement < 60 OR compa < 0.85 OR 24+ months without
        promotion — kept in sync with the generator by a test). Comparing
        treated at-risk people to the whole healthy workforce would flatter
        the program enormously.

     2. Involuntary exits are excluded. A dismissal is not a retention
        failure, and counting it as one punishes the program for decisions
        it doesn't own.

     3. Minimum-runway filter (120 days between hire and exit/snapshot) on
        the WHOLE cohort, not just the treated. Short-tenure quitters could
        never have received an intervention; leaving them in the control
        group stacks it with fast exits and inflates the measured lift
        (immortal-time bias).

   THE HONEST CAVEAT: treated employees are hand-picked, not randomized, so
   this comparison is descriptive, not causal. On this synthetic data the
   effect is planted by the generator and the analysis demonstrates the
   mechanics of recovering it. On real data the next step is an A/B'd
   intervention program or matching on risk score.

   Produces intervention_effectiveness (control row + any-intervention row +
   one row per intervention type). Runs as-is on SQLite (engine).
   =========================================================================== */

DROP TABLE IF EXISTS intervention_effectiveness;
CREATE TABLE intervention_effectiveness AS
WITH cohort AS (
    SELECT
        e.employee_id,
        e.is_active,
        CASE WHEN i.employee_id IS NOT NULL THEN 1 ELSE 0 END AS treated,
        i.intervention_type
    FROM fact_employees e
    LEFT JOIN fact_hr_interventions i ON e.employee_id = i.employee_id
    WHERE (e.engagement_score < 60
           OR e.compa_ratio < 0.85
           OR e.months_since_promotion > 24)
      AND e.term_type <> 'Involuntary'
      AND julianday(CASE WHEN e.termination_date <> '' THEN e.termination_date
                         ELSE (SELECT snapshot_date FROM params) END)
          - julianday(e.hire_date) >= 120
),
control AS (
    SELECT COUNT(*) AS n, SUM(is_active) AS retained
    FROM cohort WHERE treated = 0
),
rows_out AS (
    SELECT 'No intervention (control)' AS cohort_label, 0 AS sort_order,
           COUNT(*) AS n_employees, SUM(is_active) AS n_retained
    FROM cohort WHERE treated = 0

    UNION ALL

    SELECT 'Any intervention', 1, COUNT(*), SUM(is_active)
    FROM cohort WHERE treated = 1

    UNION ALL

    SELECT intervention_type, 2, COUNT(*), SUM(is_active)
    FROM cohort WHERE treated = 1
    GROUP BY intervention_type
)
SELECT
    r.cohort_label,
    r.sort_order,
    r.n_employees,
    r.n_retained,
    ROUND(r.n_retained * 1.0 / r.n_employees, 4) AS retention_rate,
    CASE WHEN r.sort_order = 0 THEN NULL
         ELSE ROUND(r.n_retained * 1.0 / r.n_employees
                    - c.retained * 1.0 / c.n, 4)
    END AS lift_vs_control
FROM rows_out r
CROSS JOIN control c
ORDER BY sort_order, cohort_label;
