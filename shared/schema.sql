-- =====================================================================
-- TFT Analysis System - SQLite schema
-- Shared by: TFT_measurement_viewer, TFT_yield_analyzer, TFT_recipe_builder
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- wafers : one row per fabricated wafer
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wafers (
    wafer_id             TEXT PRIMARY KEY,             -- e.g. "W_20260618_001"
    wafer_name           TEXT,
    fabrication_date     DATETIME,
    process_node         TEXT,                         -- e.g. "5µm", "10µm"
    substrate_material   TEXT,                         -- e.g. "glass", "plastic"
    initial_device_count INTEGER,                      -- total TFTs on wafer
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- tft_measurements : one row per measured device
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tft_measurements (
    measurement_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    wafer_id              TEXT NOT NULL,
    device_id             TEXT NOT NULL,               -- "D_001".. unique per wafer
    position_x            REAL,                         -- mm
    position_y            REAL,                         -- mm
    vth                   REAL,                         -- threshold voltage (V)
    mobility              REAL,                         -- carrier mobility (cm^2/Vs)
    on_off_ratio          REAL,                         -- Ion/Ioff (log10 value)
    subthreshold_swing    REAL,                         -- SS (mV/dec)
    max_drain_current     REAL,                         -- A
    leakage_current       REAL,                         -- off-state leakage (A)
    is_functional         BOOLEAN,                      -- pass/fail
    defect_type           TEXT,                         -- NULL | open_circuit | short | high_vth | low_mobility ...
    measurement_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes                 TEXT,
    FOREIGN KEY (wafer_id) REFERENCES wafers (wafer_id) ON DELETE CASCADE,
    UNIQUE (wafer_id, device_id)
);

CREATE INDEX IF NOT EXISTS idx_meas_wafer ON tft_measurements (wafer_id);
CREATE INDEX IF NOT EXISTS idx_meas_functional ON tft_measurements (wafer_id, is_functional);

-- ---------------------------------------------------------------------
-- quality_criteria : pass/fail thresholds applied to measurements
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_criteria (
    criteria_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_name  TEXT NOT NULL,                      -- e.g. "vth_min", "mobility_min"
    target_value    REAL,
    tolerance_lower REAL,
    tolerance_upper REAL,
    is_active       BOOLEAN DEFAULT 1,
    description     TEXT
);

-- ---------------------------------------------------------------------
-- recipes : fabrication recipe header
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
    recipe_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_name        TEXT UNIQUE NOT NULL,
    substrate_type     TEXT,
    target_process_node TEXT,
    description        TEXT,
    created_date       DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_modified_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active          BOOLEAN DEFAULT 1
);

-- ---------------------------------------------------------------------
-- recipe_steps : ordered process steps belonging to a recipe
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipe_steps (
    step_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id    INTEGER NOT NULL,
    step_order   INTEGER NOT NULL,
    process_type TEXT,                                  -- deposition | lithography | etching | annealing | cleaning
    process_name TEXT,                                  -- e.g. "PECVD_SiO2"
    temperature  REAL,                                  -- deg C
    duration     REAL,                                  -- minutes
    gas_mixture  TEXT,                                  -- JSON string
    pressure     REAL,                                  -- mTorr
    power        REAL,                                  -- W
    notes        TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes (recipe_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_recipe ON recipe_steps (recipe_id, step_order);

-- ---------------------------------------------------------------------
-- yield_metrics : cached yield calculation results per wafer
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS yield_metrics (
    metric_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    wafer_id                 TEXT NOT NULL,
    calculation_timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_devices            INTEGER,
    functional_devices       INTEGER,
    overall_yield_percentage REAL,
    vth_pass_count           INTEGER,
    mobility_pass_count      INTEGER,
    on_off_ratio_pass_count  INTEGER,
    defect_density_per_cm2   REAL,
    dominant_defect_type     TEXT,
    notes                    TEXT,
    FOREIGN KEY (wafer_id) REFERENCES wafers (wafer_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_yield_wafer ON yield_metrics (wafer_id);

-- =====================================================================
-- Raw I-V sweep ingest (file -> run/bias-group -> point hierarchy)
-- Stores only raw measurement points; derived parameters (Vth, mobility,
-- ...) are computed downstream and live in separate tables.
-- =====================================================================

-- One row per ingested file (one sweep test set).
CREATE TABLE IF NOT EXISTS iv_sweeps (
    sweep_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL UNIQUE,   -- original filename, used to dedupe re-ingestion
    run_start       INTEGER,                -- starting run number from filename (e.g. 889, 2721)
    sweep_type      TEXT,                   -- "IdVd" | "IdVg"
    temperature_c   REAL,
    die_col_row     TEXT,                   -- e.g. "C4R2"
    subdie_col_row  TEXT,                   -- e.g. "c1r2"
    channel_length  REAL,                   -- um
    channel_width   REAL,                   -- um
    instrument_ch   TEXT,
    material_stack  TEXT,                   -- e.g. "TiPt"
    extra_temp_c    REAL,                   -- second "200C" field, meaning TBD
    wafer_id        TEXT,                   -- optional link to wafers.wafer_id
    imported_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wafer_id) REFERENCES wafers (wafer_id) ON DELETE SET NULL
);

-- One row per "Run<N>" sheet, or per bias-group within a sheet that has
-- numbered column groups like DrainI(1)/DrainI(2)/...
CREATE TABLE IF NOT EXISTS iv_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sweep_id      INTEGER NOT NULL,
    run_number    INTEGER NOT NULL,         -- parsed from sheet name, e.g. Run2721 -> 2721
    sheet_name    TEXT,                     -- original sheet name, kept for traceability
    bias_group    INTEGER,                  -- 1/2/3... for numbered column groups, else NULL
    FOREIGN KEY (sweep_id) REFERENCES iv_sweeps (sweep_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ivruns_sweep ON iv_runs (sweep_id);

-- One row per raw measurement point within a run.
CREATE TABLE IF NOT EXISTS iv_points (
    point_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    point_order INTEGER NOT NULL,           -- row order within the sweep (preserves direction)
    drain_i     REAL,
    drain_v     REAL,
    gate_i      REAL,
    gate_v      REAL,
    FOREIGN KEY (run_id) REFERENCES iv_runs (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ivpoints_run ON iv_points (run_id, point_order);

-- =====================================================================
-- tft_curve_features : parameters computed from raw I-V sweeps
-- (the TFT analogue of the memristor "feature_switching" table).
-- One row per analysed transfer (Id-Vg) sweep.
-- =====================================================================
CREATE TABLE IF NOT EXISTS tft_curve_features (
    feature_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    sweep_id      INTEGER,                 -- FK to iv_sweeps (the Id-Vg sweep), if ingested
    source_file   TEXT UNIQUE,             -- traceability + idempotent re-save
    vth           REAL,                    -- threshold voltage (V)
    mu_sat        REAL,                    -- saturation mobility (cm^2/Vs)
    ss_min        REAL,                    -- subthreshold swing (mV/dec)
    on_off_ratio  REAL,
    ion           REAL,
    ioff          REAL,
    gm_max        REAL,
    gm_max_vg     REAL,
    cox           REAL,                    -- F/cm^2 used
    w_um          REAL,
    l_um          REAL,
    tox_nm        REAL,
    eps_r         REAL,
    computed_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sweep_id) REFERENCES iv_sweeps (sweep_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_features_sweep ON tft_curve_features (sweep_id);
