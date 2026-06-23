"""Constants and default values for the measurement viewer."""

from __future__ import annotations

APP_NAME: str = "TFT Measurement Viewer"
APP_VERSION: str = "1.0.0"
ORG_NAME: str = "TFT Analysis System"

# Default window geometry (x, y, width, height).
WINDOW_GEOMETRY: tuple[int, int, int, int] = (80, 80, 1280, 800)

# Plot styling.
HEATMAP_CMAP: str = "viridis"
PASS_COLOR: str = "#2ca02c"
FAIL_COLOR: str = "#d62728"
POINT_SIZE: int = 60

# Available plot modes shown in the plot panel selector.
PLOT_MODES: list[str] = [
    "Spatial Map",
    "Histogram",
    "Parameter Correlation",
]

# Whether to apply the bundled dark stylesheet on startup.
DARK_MODE_DEFAULT: bool = True
