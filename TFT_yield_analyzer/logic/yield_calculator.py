"""Yield metric calculation for a single wafer.

Combines per-device measurements with the shared quality criteria to produce a
:class:`YieldMetrics` summary, and can persist that summary to the
``yield_metrics`` table.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from TFT_yield_analyzer.bootstrap import config
from shared.criteria import QualityCriteria, evaluate_device

logger = logging.getLogger(__name__)


@dataclass
class YieldMetrics:
    """Computed yield summary for one wafer (mirrors the yield_metrics table)."""

    wafer_id: str
    total_devices: int
    functional_devices: int
    overall_yield_percentage: float
    vth_pass_count: int
    mobility_pass_count: int
    on_off_ratio_pass_count: int
    defect_density_per_cm2: float
    dominant_defect_type: Optional[str]
    # Extra detail kept for the dashboard (not stored in the table).
    ss_pass_count: int = 0
    leakage_pass_count: int = 0

    def as_table_row(self) -> dict:
        """Return only the columns that belong in the yield_metrics table."""
        data = asdict(self)
        data.pop("ss_pass_count", None)
        data.pop("leakage_pass_count", None)
        return data


def estimate_wafer_area_cm2(df: pd.DataFrame) -> float:
    """Estimate wafer area from the device position bounding box.

    Args:
        df: Measurement DataFrame containing ``position_x`` / ``position_y`` (mm).

    Returns:
        Area in cm^2. Falls back to :data:`config.DEFAULT_WAFER_AREA_CM2` when
        positions are missing or collapse to a line/point.
    """
    if df.empty or "position_x" not in df or "position_y" not in df:
        return config.DEFAULT_WAFER_AREA_CM2
    xs = pd.to_numeric(df["position_x"], errors="coerce").dropna()
    ys = pd.to_numeric(df["position_y"], errors="coerce").dropna()
    if xs.empty or ys.empty:
        return config.DEFAULT_WAFER_AREA_CM2
    width_mm = float(xs.max() - xs.min())
    height_mm = float(ys.max() - ys.min())
    area_mm2 = width_mm * height_mm
    if area_mm2 <= 0:
        return config.DEFAULT_WAFER_AREA_CM2
    return area_mm2 / 100.0  # mm^2 -> cm^2


def calculate_yield(
    wafer_id: str, df: pd.DataFrame, criteria: QualityCriteria
) -> YieldMetrics:
    """Calculate yield metrics for one wafer.

    Functionality is recomputed from the criteria (not trusted from the stored
    ``is_functional`` flag) so that changing criteria re-grades devices.

    Args:
        wafer_id: The wafer identifier.
        df: Measurement DataFrame for that wafer.
        criteria: Active quality criteria.

    Returns:
        A populated :class:`YieldMetrics`.
    """
    total = len(df)
    if total == 0:
        return YieldMetrics(wafer_id, 0, 0, 0.0, 0, 0, 0, 0.0, None)

    functional = 0
    param_pass = Counter()
    defect_counter: Counter[str] = Counter()

    for record in df.to_dict("records"):
        is_func, checks = evaluate_device(record, criteria)
        functional += int(is_func)
        # Group the two Vth bounds into a single "vth" pass.
        if checks.get("vth_min", True) and checks.get("vth_max", True):
            param_pass["vth"] += 1
        if checks.get("mobility_min", True):
            param_pass["mobility"] += 1
        if checks.get("on_off_ratio_min", True):
            param_pass["on_off_ratio"] += 1
        if checks.get("subthreshold_swing_max", True):
            param_pass["ss"] += 1
        if checks.get("leakage_current_max", True):
            param_pass["leakage"] += 1
        if not is_func:
            defect = record.get("defect_type") or "unclassified"
            defect_counter[defect] += 1

    area_cm2 = estimate_wafer_area_cm2(df)
    defective = total - functional
    dominant = defect_counter.most_common(1)[0][0] if defect_counter else None

    return YieldMetrics(
        wafer_id=wafer_id,
        total_devices=total,
        functional_devices=functional,
        overall_yield_percentage=round(functional / total * 100.0, 2),
        vth_pass_count=param_pass["vth"],
        mobility_pass_count=param_pass["mobility"],
        on_off_ratio_pass_count=param_pass["on_off_ratio"],
        defect_density_per_cm2=round(defective / area_cm2, 4) if area_cm2 else 0.0,
        dominant_defect_type=dominant,
        ss_pass_count=param_pass["ss"],
        leakage_pass_count=param_pass["leakage"],
    )
