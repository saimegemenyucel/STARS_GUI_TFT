"""Validation of measurement values for display sanity checks.

The viewer is read-only, but data imported by external tools can contain
out-of-range or physically impossible values. These helpers flag such rows so
the UI can warn the user rather than silently plotting garbage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Physically plausible ranges for sanity checking (not pass/fail criteria).
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "vth": (-20.0, 20.0),
    "mobility": (0.0, 500.0),
    "on_off_ratio": (0.0, 15.0),
    "subthreshold_swing": (0.0, 5000.0),
    "max_drain_current": (0.0, 1.0),
    "leakage_current": (0.0, 1.0),
}


@dataclass
class ValidationReport:
    """Summary of validation issues found in a measurement set."""

    total_rows: int
    issues: dict[str, int]  # column -> count of out-of-range / null values

    @property
    def has_issues(self) -> bool:
        """True if any column reported at least one problematic value."""
        return any(count > 0 for count in self.issues.values())

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        if not self.has_issues:
            return f"All {self.total_rows} rows valid."
        parts = [f"{col}: {n}" for col, n in self.issues.items() if n]
        return f"{self.total_rows} rows; flagged -> " + ", ".join(parts)


def validate_measurements(df: pd.DataFrame) -> ValidationReport:
    """Check a measurement DataFrame for nulls and out-of-range values.

    Args:
        df: Measurement DataFrame (as returned by ``db_ops.load_measurements``).

    Returns:
        A :class:`ValidationReport` describing how many values per column are
        null or fall outside :data:`PLAUSIBLE_RANGES`.
    """
    issues: dict[str, int] = {}
    for col, (lo, hi) in PLAUSIBLE_RANGES.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        out_of_range = ((series < lo) | (series > hi)).sum()
        nulls = series.isna().sum()
        issues[col] = int(out_of_range + nulls)
    return ValidationReport(total_rows=len(df), issues=issues)


def clean_for_plot(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Drop rows where ``column`` (or position) is null/non-finite, for plotting.

    Args:
        df: Source measurement DataFrame.
        column: The parameter column being plotted.

    Returns:
        A filtered copy safe to pass to matplotlib.
    """
    needed = [c for c in (column, "position_x", "position_y") if c in df.columns]
    out = df.copy()
    for col in needed:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=needed)
    return out
