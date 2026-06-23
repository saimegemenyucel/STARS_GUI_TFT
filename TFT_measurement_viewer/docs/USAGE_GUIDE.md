# Measurement Viewer — Usage Guide

## Launching

```bash
python init_database.py            # once, creates TFT_Database.db
python TFT_measurement_viewer/run.py
```

## Window layout

| Area | Contents |
|------|----------|
| Left | Wafer list (top) and the **Filters** group (bottom) |
| Centre | Sortable measurement table; green rows pass, red rows fail |
| Right | Wafer metadata (top) and the plot panel (bottom) |

Drag the splitter handles to resize any panel.

## Selecting and filtering

1. Click a wafer in the list. Its devices load into the table and plots, and
   the metadata box updates.
2. Use the **Filters** group to narrow the view (all filtering is instant):
   - **Status** — All / Functional only / Failed only.
   - **Defect type** — populated from the selected wafer's defects.
   - **Parameter / Min / Max** — keep only devices whose chosen parameter falls
     within the range.
3. The status bar shows the device count, functional count, live yield %, and a
   data-validation summary.

## Plots

Pick a mode in the plot panel:

- **Spatial Map** — device positions coloured by the chosen parameter (current
  and leakage are shown on a log scale).
- **Histogram** — distribution of the chosen parameter, split by pass/fail.
- **Parameter Correlation** — scatter of two parameters (e.g. Vth vs Mobility).

Use the matplotlib toolbar to zoom, pan and save any plot as an image.

## Exporting

`File ▸ Export filtered to CSV…` (Ctrl+E) writes the currently filtered table to
a CSV file.

## Shortcuts

| Key | Action |
|-----|--------|
| F5 | Reload wafer list |
| Ctrl+E | Export filtered measurements |
| Ctrl+Q | Quit |
