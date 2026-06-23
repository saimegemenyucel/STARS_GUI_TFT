"""Constants and default values for the yield analyzer."""

from __future__ import annotations

APP_NAME: str = "TFT Yield Analyzer"
APP_VERSION: str = "1.0.0"
ORG_NAME: str = "TFT Analysis System"

WINDOW_GEOMETRY: tuple[int, int, int, int] = (90, 90, 1280, 820)

# Fallback wafer area (cm^2) used for defect-density when device positions do
# not span a measurable area. ~100 mm wafer => pi * 5cm^2.
DEFAULT_WAFER_AREA_CM2: float = 78.54

# Number of grid cells per axis for spatial defect hotspot binning.
HOTSPOT_GRID: int = 6

PASS_COLOR: str = "#2ca02c"
FAIL_COLOR: str = "#d62728"
HEATMAP_CMAP: str = "magma"

DARK_MODE_DEFAULT: bool = True
