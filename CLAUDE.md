# STARS_GUI_TFT

PyQt6 suite for Thin-Film-Transistor (TFT) wafer characterization, yield
analysis, and fabrication recipe management. Three independent desktop apps
share one SQLite database (`TFT_Database.db`, schema in `shared/schema.sql`).

## Modules

| Module | Purpose | Entry point |
|---|---|---|
| `TFT_measurement_viewer` | Browse per-device measurements, spatial/histogram/correlation plots, raw I-V curve analysis | `python TFT_measurement_viewer/run.py` |
| `TFT_yield_analyzer` | Yield %, defect density, hotspot detection, wafer map | `python TFT_yield_analyzer/run.py` |
| `TFT_recipe_builder` | Create/edit fabrication recipes and device-structure cross-sections | `python TFT_recipe_builder/run.py` |

Each module has the same internal shape: `bootstrap/` (Qt app + config),
`ui/`, `sql/` (db_ops), `logic/`, `run.py`, `smoke_import.py`.

`shared/` holds everything common to all three: DB connection (`db.py`),
schema (`schema.sql`), pass/fail rules (`criteria.py`), the TFT curve-analysis
engine (`tft_analysis.py`), I-V file ingestion (`iv_ingest.py`), wafer-map
building (`wafer_map.py`), Qt table model / widgets, plotting helpers, and
`logging_setup.py`.

## Setup

```bash
pip install -r requirements.txt
python init_database.py                       # idempotent; seeds default IGZO criteria
python TFT_measurement_viewer/run.py           # or _yield_analyzer / _recipe_builder
```

## Tests

```bash
pip install pytest
pytest                                          # unit tests for shared/ and logic/ (pure functions, no Qt/DB needed)
python TFT_measurement_viewer/smoke_import.py   # + _yield_analyzer / _recipe_builder
```

CI (`.github/workflows/ci.yml`) runs both on every push/PR across Python 3.10-3.12.

## Generating test data

`tools/make_artificial_wafer.py` writes a synthetic wafer of Id-Vg/Id-Vd
`.xlsx` files with a known mix of good/weak/dead devices, importable through
Yield Analyzer ▸ Wafer Map ▸ "Load wafer folder…":

```bash
python tools/make_artificial_wafer.py [base_folder] [--per-die N] [--die-coverage F]
```

Default output folder is `~/Desktop/Wafers/Artificial Data Wafer`.

## Key gotcha: unphysical mobility from near-singularity divisions

Two functions in `shared/tft_analysis.py` extract mobility by fitting/dividing
through quantities that can pass through (or near) zero, and both used to let
that produce nonsensical, billions-of-cm^2/Vs results:

- `_sqrt_extrapolation` (drives `mu_sat`): fits sqrt(|Id|) vs Vg near its
  steepest slope. For a device whose current never rises meaningfully above
  the noise/off floor within the swept range (e.g. a "dead" transistor with
  very low mobility and very high subthreshold swing), the steepest-slope
  search used to lock onto pure measurement noise, and since mobility scales
  with `slope**2`, that noise got squared into huge values. Fixed by
  smoothing before differentiating and rejecting the fit (NaN) when the
  sqrt(Id) excursion isn't clearly above the noise level.
- `average_mobility` (drives `mu_avg` / `mu_avg_peak`, the "μ_AVG peak
  (linear, Zhou)" value shown in the curve analysis panel): divides Id by
  `overdrive * vch`. The old `abs(x) > 1e-9` guard only rejected points
  within ~1 nV of the singularity, not points merely *close* to it (which
  still blow the denominator up to a huge-but-finite value) — this shows up
  whenever `rc_ohm > 0` makes `vch` data-dependent. Fixed by requiring both
  `overdrive` and `vch` to be at least 0.05 V from zero.

Both now also reject (NaN) any result exceeding `MAX_PHYSICAL_MU_SAT_CM2VS`
(500 cm^2/Vs — generous headroom above realistic oxide-TFT mobilities) as a
final backstop. See `tests/test_tft_analysis.py` for regression tests
covering the dead-device, near-singularity, and normal-device cases.

## Conventions

- Type hints + Google-style docstrings throughout; `from __future__ import annotations`.
- `pathlib` for all paths; `shared/paths.py` is the single source for
  `PROJECT_ROOT` / `DB_PATH` (override with `TFT_DB_PATH` env var for tests).
- Broad `except Exception` blocks in `ui/` files are intentional top-level
  guards around user-triggered actions (file load, DB query, plotting): they
  always `logger.exception(...)` and show a `QMessageBox` rather than crash
  the app silently. Keep that pattern when adding new UI handlers.
- Logging: call `shared.logging_setup.configure_logging(app_name)` once at
  app startup (already wired in each module's `bootstrap/qt_app.py`); it
  attaches both a console handler and a rotating file handler under `logs/`.
