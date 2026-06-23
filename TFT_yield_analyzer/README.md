# TFT Yield Analyzer

Calculate wafer yield, identify defect patterns, and persist yield metrics.

## Features

- Overall yield % (functional / total), recomputed live from the shared
  `quality_criteria` so changing thresholds re-grades devices.
- Per-parameter pass counts (Vth, mobility, on/off ratio, SS, leakage).
- Defect density per cm² (wafer area estimated from device positions).
- Dominant defect-type identification and full defect breakdown.
- Grid-based spatial **hotspot** detection for clustered failures.
- Defect map, KPI dashboard, parameter statistics table, and a saved-metric
  history tab.
- Save calculated metrics to the `yield_metrics` table.

## Run

```bash
pip install -r requirements.txt
python init_database.py          # from project root, safe to re-run
python TFT_yield_analyzer/run.py
```

## Workflow

1. Select a wafer in the left list.
2. Click **Calculate Yield** to populate the Dashboard and Defect Map tabs.
3. Click **Save Metrics to DB** (Ctrl+S) to record the result in the
   `yield_metrics` table; it then appears in the **Metric History** tab.

## Smoke test

```bash
python TFT_yield_analyzer/smoke_import.py
```

See `docs/ARCHITECTURE.md` and `docs/METRICS_DEFINITION.md`.
