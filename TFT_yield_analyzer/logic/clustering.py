"""Lightweight spatial clustering of failed devices.

Avoids heavy ML dependencies: failures are binned onto a coarse grid and the
densest cells are reported as hotspots. This is enough to flag spatially
correlated defects (e.g. an edge ring or a particle streak).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from TFT_yield_analyzer.bootstrap import config

logger = logging.getLogger(__name__)


@dataclass
class Hotspot:
    """A grid cell with an elevated failure count."""

    x_center: float
    y_center: float
    fail_count: int
    total_count: int

    @property
    def fail_fraction(self) -> float:
        """Fraction of devices in the cell that failed."""
        return self.fail_count / self.total_count if self.total_count else 0.0


def find_hotspots(
    df: pd.DataFrame, grid: int | None = None, min_fail_fraction: float = 0.5
) -> list[Hotspot]:
    """Bin devices onto a grid and return cells dominated by failures.

    Args:
        df: Measurement DataFrame with positions and ``is_functional``.
        grid: Number of cells per axis (defaults to :data:`config.HOTSPOT_GRID`).
        min_fail_fraction: Minimum failed fraction for a cell to count as a
            hotspot.

    Returns:
        Hotspots sorted by descending fail fraction then fail count.
    """
    grid = grid or config.HOTSPOT_GRID
    data = df.copy()
    for col in ("position_x", "position_y"):
        data[col] = pd.to_numeric(data.get(col), errors="coerce")
    data = data.dropna(subset=["position_x", "position_y"])
    if data.empty:
        return []

    xs = data["position_x"].to_numpy()
    ys = data["position_y"].to_numpy()
    failed = (data["is_functional"] != True).to_numpy()  # noqa: E712

    x_edges = np.linspace(xs.min(), xs.max(), grid + 1)
    y_edges = np.linspace(ys.min(), ys.max(), grid + 1)
    # np.digitize gives 1..grid; clip the top edge into the last bin.
    xi = np.clip(np.digitize(xs, x_edges) - 1, 0, grid - 1)
    yi = np.clip(np.digitize(ys, y_edges) - 1, 0, grid - 1)

    hotspots: list[Hotspot] = []
    for cx in range(grid):
        for cy in range(grid):
            mask = (xi == cx) & (yi == cy)
            total = int(mask.sum())
            if total == 0:
                continue
            fails = int(failed[mask].sum())
            if total and (fails / total) >= min_fail_fraction and fails > 0:
                hotspots.append(Hotspot(
                    x_center=float((x_edges[cx] + x_edges[cx + 1]) / 2),
                    y_center=float((y_edges[cy] + y_edges[cy + 1]) / 2),
                    fail_count=fails,
                    total_count=total,
                ))
    hotspots.sort(key=lambda h: (h.fail_fraction, h.fail_count), reverse=True)
    return hotspots
