/* ===========================================================================
   01_schema.sql  —  People Analytics warehouse schema (reference DDL)

   Canonical star schema for the HR attrition & retention mart, written in
   T-SQL (SQL Server / Microsoft Fabric Warehouse dialect). The runnable
   engine (engine/run_hr_analytics.py) loads the same tables into SQLite from
   the CSVs in data/, then executes the analytics in sql/02..09 against them.

   Grain
     dim_department / dim_job / dim_location / dim_date : conformed dimensions
     fact_employees      : one row per employee (current + former), point-in-
                           time snapshot as of 2026-06-30
     comp_benchmark      : external market pay by job level
     fact_applications   : one row per job application (recruiting funnel)
     fact_hr_interventions : one row per retention action taken on an
                           at-risk employee (stay interview, raise, ...)
   =========================================================================== */

CREATE TABLE dim_department (
    department_id  INT          NOT NULL PRIMARY KEY,
    department     VARCHAR(60)  NOT NULL,
    division       VARCHAR(40)  NOT NULL
);

CREATE TABLE dim_job (
    job_id         INT          NOT NULL PRIMARY KEY,
    job_title      VARCHAR(60)  NOT NULL,
    job_level      VARCHAR(40)  NOT NULL,   -- Associate .. Director
    level_rank     INT          NOT NULL,   -- 1..8 ordinal seniority
    is_management  BIT          NOT NULL
);

CREATE TABLE dim_location (
    location_id    INT          NOT NULL PRIMARY KEY,
    city           VARCHAR(60)  NOT NULL,
    region         VARCHAR(40)  NOT NULL,
    country        VARCHAR(40)  NOT NULL,
    is_remote      BIT          NOT NULL
);

CREATE TABLE dim_date (
    month          CHAR(7)      NOT NULL PRIMARY KEY,  -- 'YYYY-MM'
    month_start    DATE         NOT NULL,
    year           INT          NOT NULL,
    quarter        VARCHAR(8)   NOT NULL,
    month_num      INT          NOT NULL
);

CREATE TABLE comp_benchmark (
    job_level      VARCHAR(40)  NOT NULL PRIMARY KEY,
    level_rank     INT          NOT NULL,
    market_p25     DECIMAL(12,2) NOT NULL,
    market_median  DECIMAL(12,2) NOT NULL,
    market_p75     DECIMAL(12,2) NOT NULL
);

CREATE TABLE fact_employees (
    employee_id            INT          NOT NULL PRIMARY KEY,
    employee_name          VARCHAR(80)  NOT NULL,   -- synthetic (Faker)
    department_id          INT          NOT NULL REFERENCES dim_department(department_id),
    job_id                 INT          NOT NULL REFERENCES dim_job(job_id),
    location_id            INT          NOT NULL REFERENCES dim_location(location_id),
    gender                 VARCHAR(20)  NOT NULL,
    ethnicity_group        VARCHAR(20)  NOT NULL,
    age_band               VARCHAR(10)  NOT NULL,
    hire_date              DATE         NOT NULL,
    termination_date       DATE         NULL,
    term_type              VARCHAR(20)  NULL,   -- Voluntary / Involuntary / NULL
    is_active              BIT          NOT NULL,
    tenure_months          DECIMAL(8,1) NOT NULL,
    base_salary            DECIMAL(12,2) NOT NULL,
    compa_ratio            DECIMAL(8,4) NOT NULL,  -- salary / market median for level
    performance_rating     INT          NOT NULL,  -- 1..5
    engagement_score       DECIMAL(6,1) NOT NULL,  -- 0..100
    overtime_hours         DECIMAL(6,1) NOT NULL,  -- monthly
    commute_km             DECIMAL(6,1) NOT NULL,
    months_since_promotion DECIMAL(8,1) NOT NULL,
    manager_id             INT          NULL REFERENCES fact_employees(employee_id),
    tenure_band            VARCHAR(10)  NOT NULL,   -- '<1 yr' .. '6+ yr'
    tenure_band_sort       INT          NOT NULL    -- 0..4 chronological sort key
);

CREATE TABLE fact_applications (
    application_id     INT          NOT NULL PRIMARY KEY,
    req_id             VARCHAR(20)  NOT NULL,
    department_id      INT          NOT NULL REFERENCES dim_department(department_id),
    job_id             INT          NOT NULL REFERENCES dim_job(job_id),
    source             VARCHAR(30)  NOT NULL,
    applied_date       DATE         NOT NULL,
    reached_screen     BIT          NOT NULL,
    reached_interview  BIT          NOT NULL,
    reached_offer      BIT          NOT NULL,
    hired              BIT          NOT NULL,
    offer_accepted     BIT          NULL,
    days_to_fill       INT          NULL
);

CREATE TABLE fact_hr_interventions (
    intervention_id    INT          NOT NULL PRIMARY KEY,
    employee_id        INT          NOT NULL REFERENCES fact_employees(employee_id),
    intervention_date  DATE         NOT NULL,
    intervention_type  VARCHAR(30)  NOT NULL    -- 'Stay interview', 'Out-of-cycle raise', ...
);

CREATE INDEX ix_emp_department ON fact_employees(department_id);
CREATE INDEX ix_emp_job        ON fact_employees(job_id);
CREATE INDEX ix_emp_active     ON fact_employees(is_active);
CREATE INDEX ix_app_source     ON fact_applications(source);
CREATE INDEX ix_int_employee   ON fact_hr_interventions(employee_id);
