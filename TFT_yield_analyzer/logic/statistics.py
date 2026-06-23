"""Descriptive statistics for wafer measurement parameters."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from shared.parameters import PARAMETERS

logger = logging.getLogger(__name__)

_STAT_PARAMS = [p.key for p in PARAMETERS]


def parameter_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute summary statistics for each electrical parameter.

    Args:
        df: Measurement DataFrame for one wafer.

    Returns:
        DataFrame indexed by parameter with columns ``mean``, ``std``, ``min``,
        ``median``, ``max`` and ``count``. Empty if there is no data.
    """
    rows = []
    for key in _STAT_PARAMS:
        if key not in df.columns:
            continue
        series = pd.to_numeric(df[key], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if series.empty:
            rows.append((key, np.nan, np.nan, np.nan, np.nan, np.nan, 0))
            continue
        rows.append((
            key,
            round(float(series.mean()), 4),
            round(float(series.std(ddof=1)) if len(series) > 1 else 0.0, 4),
            round(float(series.min()), 4),
            round(float(series.median()), 4),
            round(float(series.max()), 4),
            int(series.count()),
        ))
    return pd.DataFrame(
        rows,
        columns=["parameter", "mean", "std", "min", "median", "max", "count"],
    ).set_index("parameter")


def defect_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Count devices by defect type (functional devices grouped as 'none').

    Args:
        df: Measurement DataFrame for one wafer.

    Returns:
        DataFrame with columns ``defect_type`` and ``count`` sorted descending.
    """
    if df.empty:
        return pd.DataFrame(columns=["defect_type", "count"])
    work = df.copy()
    functional = work["is_functional"] == True  # noqa: E712
    work.loc[functional, "defect_type"] = "none"
    work["defect_type"] = work["defect_type"].fillna("unclassified")
    counts = (
        work["defect_type"].value_counts().rename_axis("defect_type")
        .reset_index(name="count")
    )
    return counts
