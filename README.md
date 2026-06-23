# TFT Analysis System

A modular PyQt6 suite for Thin-Film-Transistor (TFT) wafer characterization,
yield analysis, and recipe management. All three modules share a single SQLite
database (`TFT_Database.db`).

## Modules

| Module | Purpose |
|--------|---------|
| **TFT_measurement_viewer** | Browse and analyse individual device measurements per wafer, with spatial maps, histograms and correlation plots. |
| **TFT_yield_analyzer** | Calculate yield %, defect density, parameter pass counts, defect hotspots, and persist yield metrics. |
| **TFT_recipe_builder** | Create, edit, version and manage fabrication recipes and their ordered process steps. |

## Project layout

```
STARS_GUI_TFT/
├── init_database.py            # create / upgrade TFT_Database.db (run first)
├── requirements.txt            # common dependencies
├── shared/                     # schema, DB connection, criteria, parameters, style, Qt models
├── TFT_measurement_viewer/
├── TFT_yield_analyzer/
├── TFT_recipe_builder/
└── sql_tools/                  # extract_schema, schema_to_erd, generate_docs
```

Each module has the same internal shape: `bootstrap/` (Qt app + config),
`ui/`, `sql/` (db_ops), `logic/`, `docs/`, plus `run.py` and `smoke_import.py`.

## Setup

```bash
# 1. Install dependencies (a virtual environment is recommended)
pip install -r requirements.txt

# 2. Create the shared database (idempotent; seeds default quality criteria)
python init_database.py

# 3. Launch any module
python TFT_measurement_viewer/run.py
python TFT_yield_analyzer/run.py
python TFT_recipe_builder/run.py
```

> The viewer and analyzer read existing wafer/measurement data. Populate the
> `wafers` and `tft_measurements` tables with your import tooling first; the
> recipe builder works standalone.

## Database

Six tables: `wafers`, `tft_measurements`, `quality_criteria`, `recipes`,
`recipe_steps`, `yield_metrics`. The canonical definition lives in
`shared/schema.sql`. Regenerate a schema dump, ERD or CSV docs with:

```bash
python sql_tools/extract_schema.py      # -> sql_tools/schema_dump.sql
python sql_tools/schema_to_erd.py       # -> sql_tools/schema_erd.svg
python sql_tools/generate_docs.py       # -> sql_tools/docs_out/*.csv
```

## Quality criteria

A device is **functional** when it passes every *active* row in
`quality_criteria` (Vth window, mobility floor, on/off floor, SS ceiling,
leakage ceiling). `init_database.py` seeds sensible IGZO defaults you can edit
directly in the database; changing them re-grades devices on the next yield
calculation.

## Smoke tests

```bash
python TFT_measurement_viewer/smoke_import.py
python TFT_yield_analyzer/smoke_import.py
python TFT_recipe_builder/smoke_import.py
```

## Tech stack

PyQt6 · SQLite · pandas · NumPy · matplotlib · SciPy. Python 3.9+.
Code style: PEP 8, type hints throughout, Google-style docstrings,
`pathlib`, `logging`.

## Raw I-V sweep ingest

Legacy `.xls`/`.xlsx` sweep files from the parametric analyzer are imported into
three linked tables — `iv_sweeps` (one per file) → `iv_runs` (one per `Run<N>`
sheet, or per numbered bias-group within a sheet) → `iv_points` (raw points).

```bash
python ingest_measurements.py <file-or-folder> [--wafer W_ID] [--replace]
```

- Filename metadata (`R<run>-IdVd/IdVg-<T>C-<die>-<subdie>_L<#>W<#>-ch<#>_<stack>-<T2>C`)
  is parsed into `iv_sweeps`; unmatched names are skipped, not fatal.
- The number of runs / bias-groups per file is **discovered dynamically**.
- Re-ingesting is idempotent (`source_file UNIQUE`); use `--replace` to overwrite.
- Only raw points are stored (Settings/Calc sheets ignored); derived parameters
  are computed separately by `shared/tft_analysis.py`.

The measurement viewer also exposes this via **File ▸ Import I-V sweeps…** (Ctrl+I).
