# Opening the Power BI dashboard

The report is committed as a **Power BI Project (PBIP)** — a TMDL semantic
model plus a PBIR report definition, both hand-authored as plain text so the
whole dashboard diffs and reviews like code.

## Open & refresh

1. Run the pipeline once so the CSVs the model reads exist:
   ```
   python data_generator/generate_hr_data.py
   python engine/run_hr_analytics.py
   python ml/attrition_model.py
   ```
2. Open `pbip/HRAttritionAnalytics.pbip` in **Power BI Desktop**
   (Store version or newer; PBIP authoring must be enabled — it is on by
   default in current releases).
3. If the data doesn't load automatically, set the **`DataPath`** parameter
   (Transform data → Edit parameters) to the absolute path of this repo on
   your machine, then **Refresh**. `DataPath` defaults to the path this
   project was generated at.

## What's inside

- **Semantic model** (`HRAttritionAnalytics.SemanticModel/`): 16 data tables
  (4 conformed dimensions, the employee master, and the SQL/ML output tables),
  5 relationships, and 39 DAX measures in a dedicated `_Measures` table.
  Percent and currency columns carry display formats, and category columns
  (funnel stage, bridge bucket, cohort year, tenure band) sort by hidden
  ordinal keys, not alphabetically. Model reads from `data/` (dimensions +
  employee master) and `output/` (SQL and ML results).
- **Report** (`HRAttritionAnalytics.Report/`): 6 pages / 53 visuals, styled
  with the shared **Meridian Corporate** theme.

| Page | Advanced visuals |
|------|------------------|
| Workforce Scorecard | KPI cards · gauge (attrition vs target) · area (headcount trend) · **waterfall** (12-mo bridge) · column |
| Attrition Deep-Dive | bar · **donut** (voluntary/involuntary) · **treemap** (exits by level) · line (rolling attrition) · column |
| Retention & Cohorts | line (survival by cohort) · **matrix** (retention triangle) · column · table |
| Pay Equity | gauge (compa-ratio) · grouped column (salary by gender) · **scatter** · table |
| Recruiting Funnel | **funnel** (pipeline) · column (source ROI) · bar (time-to-fill) · table |
| Flight Risk (ML) | **treemap** · donut (risk bands) · **scatter** (tenure × engagement) · watch-list table |

The measure definitions are mirrored in [`dax_measures.dax`](dax_measures.dax)
for quick reading. `tests/test_powerbi_integrity.py` verifies on every push
that every visual still binds to a real column or measure.
