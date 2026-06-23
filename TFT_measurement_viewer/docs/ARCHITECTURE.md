# Measurement Viewer — Architecture

## Layering

```
run.py
  └─ bootstrap/qt_app.py        # QApplication, stylesheet, DB init
       └─ ui/main_window.py     # orchestrates widgets + filtering
            ├─ ui/measurement_table.py   # QTableView + DataFrame model
            ├─ ui/plot_panel.py          # matplotlib canvas + selectors
            ├─ sql/db_ops.py             # read queries (pandas)
            └─ logic/                    # validation + plotting routines
shared/                          # DB, criteria, parameters, style, Qt models
```

The module depends on the `shared` package (one directory up) for the database
connection, parameter metadata, the dark stylesheet, and the reusable
`DataFrameModel`. `run.py` inserts the project root onto `sys.path` so these
imports resolve no matter where the script is launched from.

## Data flow & performance

1. **Startup:** `db_ops.load_wafer_metadata()` runs one lightweight query that
   returns a row per wafer plus a measured-device count. The (potentially
   large) measurement rows are **not** loaded yet.
2. **Wafer selected:** `db_ops.load_measurements(wafer_id)` lazily loads that
   wafer's devices into a pandas DataFrame held in `MainWindow._all_measurements`.
3. **Filtering:** all filters (status, defect type, parameter range) are applied
   **in memory** against the cached DataFrame — no extra SQL — so the UI stays
   responsive. The filtered frame feeds both the table and the plot panel.

## Key decisions

- **pandas as the in-memory model.** Filtering and CSV export are trivial, and
  `DataFrameModel` adapts a frame to Qt's model/view directly.
- **Figures drawn by pure functions** in `logic/plot_helpers.py` that take a
  `Figure`. This keeps plotting testable and reusable for off-screen export.
- **Read-only by design.** The viewer never writes measurement data; pass/fail
  evaluation rules live in `shared/criteria.py` and are reused by the analyzer.
