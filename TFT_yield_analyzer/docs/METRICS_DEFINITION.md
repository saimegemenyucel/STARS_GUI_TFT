# Yield Metric Definitions

| Metric | Definition |
|--------|------------|
| **Overall yield %** | `functional_devices / total_devices × 100`. A device is functional only if it passes every active quality criterion. |
| **Functional device** | Passes all active checks in `quality_criteria`: Vth within `[vth_min, vth_max]`, mobility ≥ `mobility_min`, on/off ratio ≥ `on_off_ratio_min`, SS ≤ `subthreshold_swing_max`, leakage ≤ `leakage_current_max`. Unenforced (inactive) criteria are skipped. |
| **Parameter pass count** | Number of devices passing that single parameter's check(s), independent of other parameters. Vth combines its min and max bounds. |
| **Defect density (/cm²)** | `defective_devices / wafer_area_cm²`. Wafer area is the bounding box of device positions (mm → cm²); if positions are missing or degenerate it falls back to `config.DEFAULT_WAFER_AREA_CM2`. |
| **Dominant defect type** | The most common `defect_type` among failed devices (`unclassified` when a failed device has no recorded type). |
| **Hotspot** | A spatial grid cell (`config.HOTSPOT_GRID` per axis) whose failed fraction ≥ the threshold (default 0.5) and contains ≥ 1 failure. Highlights spatially clustered defects such as edge rings or particle streaks. |

## Notes

- Criteria are read live from the database, so re-running a calculation after
  editing `quality_criteria` reflects the new thresholds immediately.
- Saved rows in `yield_metrics` are a historical log; each Save appends a new
  timestamped row rather than overwriting.
