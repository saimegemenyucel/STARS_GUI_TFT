-- Auto-extracted schema

CREATE TABLE iv_points (
    point_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    point_order INTEGER NOT NULL,           -- row order within the sweep (preserves direction)
    drain_i     REAL,
    drain_v     REAL,
    gate_i      REAL,
    gate_v      REAL,
    FOREIGN KEY (run_id) REFERENCES iv_runs (run_id) ON DELETE CASCADE
);

CREATE TABLE iv_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sweep_id      INTEGER NOT NULL,
    run_number    INTEGER NOT NULL,         -- parsed from sheet name, e.g. Run2721 -> 2721
    sheet_name    TEXT,                     -- original sheet name, kept for traceability
    bias_group    INTEGER,                  -- 1/2/3... for numbered column groups, else NULL
    FOREIGN KEY (sweep_id) REFERENCES iv_sweeps (sweep_id) ON DELETE CASCADE
);

CREATE TABLE iv_sweeps (
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

CREATE TABLE quality_criteria (
    criteria_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_name  TEXT NOT NULL,                      -- e.g. "vth_min", "mobility_min"
    target_value    REAL,
    tolerance_lower REAL,
    tolerance_upper REAL,
    is_active       BOOLEAN DEFAULT 1,
    description     TEXT
);

CREATE TABLE recipe_steps (
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

CREATE TABLE recipes (
    recipe_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_name        TEXT UNIQUE NOT NULL,
    substrate_type     TEXT,
    target_process_node TEXT,
    description        TEXT,
    created_date       DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_modified_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active          BOOLEAN DEFAULT 1
);

CREATE TABLE tft_curve_features (
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

CREATE TABLE tft_measurements (
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

CREATE TABLE wafers (
    wafer_id             TEXT PRIMARY KEY,             -- e.g. "W_20260618_001"
    wafer_name           TEXT,
    fabrication_date     DATETIME,
    process_node         TEXT,                         -- e.g. "5µm", "10µm"
    substrate_material   TEXT,                         -- e.g. "glass", "plastic"
    initial_device_count INTEGER,                      -- total TFTs on wafer
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE yield_metrics (
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

CREATE INDEX idx_features_sweep ON tft_curve_features (sweep_id);

CREATE INDEX idx_ivpoints_run ON iv_points (run_id, point_order);

CREATE INDEX idx_ivruns_sweep ON iv_runs (sweep_id);

CREATE INDEX idx_meas_functional ON tft_measurements (wafer_id, is_functional);

CREATE INDEX idx_meas_wafer ON tft_measurements (wafer_id);

CREATE INDEX idx_step_recipe ON recipe_steps (recipe_id, step_order);

CREATE INDEX idx_yield_wafer ON yield_metrics (wafer_id);
