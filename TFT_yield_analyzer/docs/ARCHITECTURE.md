# Yield Analyzer — Architecture

## Layering

```
run.py
  └─ bootstrap/qt_app.py
       └─ ui/main_window.py
            ├─ ui/yield_dashboard.py     # KPI cards + bar chart + stats table
            ├─ ui/defect_map_viewer.py   # spatial pass/fail + hotspot rings
            ├─ sql/db_ops.py             # reads + yield_metrics persistence
            └─ logic/
                 ├─ yield_calculator.py  # YieldMetrics + defect density
                 ├─ statistics.py        # per-parameter descriptive stats
                 └─ clustering.py        # grid hotspot detection (numpy only)
shared/                                  # criteria, parameters, DB, style
```

## Design notes

- **Criteria-driven grading.** `calculate_yield` re-evaluates each device with
  `shared.criteria.evaluate_device` rather than trusting the stored
  `is_functional` flag, so editing `quality_criteria` changes the result.
- **No heavy ML dependency.** Hotspot detection bins devices onto a coarse grid
  (`config.HOTSPOT_GRID`) and flags cells whose failure fraction exceeds a
  threshold — robust and dependency-light (numpy only).
- **Calculation vs persistence are separate.** `YieldMetrics` is computed
  in-memory; only an explicit Save writes a row to `yield_metrics`. The
  `as_table_row()` helper drops dashboard-only fields not in the schema.
- **Plots are widgets** that take a DataFrame/metrics object, keeping the main
  window thin.
