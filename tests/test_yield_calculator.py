"""Tests for TFT_yield_analyzer.logic.yield_calculator."""

from __future__ import annotations

import pandas as pd

from shared.criteria import QualityCriteria
from TFT_yield_analyzer.logic.yield_calculator import calculate_yield, estimate_wafer_area_cm2


def test_calculate_yield_counts_functional_devices():
    df = pd.DataFrame([
        {"position_x": 0, "position_y": 0, "vth": 0.0, "mobility": 10.0,
         "on_off_ratio": 1e6, "subthreshold_swing": 100.0,
         "leakage_current": 1e-10, "defect_type": None},
        {"position_x": 1, "position_y": 0, "vth": 0.0, "mobility": 0.1,
         "on_off_ratio": 1e6, "subthreshold_swing": 100.0,
         "leakage_current": 1e-10, "defect_type": "low_mobility"},
    ])
    criteria = QualityCriteria(mobility_min=5.0)

    metrics = calculate_yield("WAFER_1", df, criteria)

    assert metrics.total_devices == 2
    assert metrics.functional_devices == 1
    assert metrics.overall_yield_percentage == 50.0
    assert metrics.mobility_pass_count == 1
    assert metrics.dominant_defect_type == "low_mobility"


def test_calculate_yield_handles_empty_dataframe():
    df = pd.DataFrame(columns=["position_x", "position_y"])

    metrics = calculate_yield("EMPTY", df, QualityCriteria())

    assert metrics.total_devices == 0
    assert metrics.functional_devices == 0
    assert metrics.overall_yield_percentage == 0.0
    assert metrics.dominant_defect_type is None


def test_estimate_wafer_area_falls_back_when_positions_missing():
    df = pd.DataFrame({"vth": [0.0, 1.0]})

    from TFT_yield_analyzer.bootstrap import config

    assert estimate_wafer_area_cm2(df) == config.DEFAULT_WAFER_AREA_CM2


def test_estimate_wafer_area_from_bounding_box():
    df = pd.DataFrame({"position_x": [0.0, 10.0], "position_y": [0.0, 10.0]})

    area = estimate_wafer_area_cm2(df)

    assert area == (10.0 * 10.0) / 100.0
