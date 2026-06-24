"""Tests for TFT_yield_analyzer.logic.clustering hotspot detection."""

from __future__ import annotations

import pandas as pd

from TFT_yield_analyzer.logic.clustering import find_hotspots


def _device(x, y, functional):
    return {"position_x": x, "position_y": y, "is_functional": functional}


def test_finds_a_dense_failure_cluster():
    rows = []
    # A 2x2 cluster of failures in one corner.
    for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        rows.append(_device(x, y, False))
    # Scattered passes elsewhere.
    for x, y in ((8, 8), (9, 9), (7, 8)):
        rows.append(_device(x, y, True))
    df = pd.DataFrame(rows)

    hotspots = find_hotspots(df, grid=4, min_fail_fraction=0.5)

    assert len(hotspots) >= 1
    assert hotspots[0].fail_fraction == 1.0
    assert hotspots[0].fail_count == 4


def test_no_hotspots_when_failures_are_sparse():
    rows = [_device(x, y, x % 5 != 0) for x in range(10) for y in range(10)]
    df = pd.DataFrame(rows)

    hotspots = find_hotspots(df, grid=4, min_fail_fraction=0.9)

    assert hotspots == []


def test_empty_dataframe_returns_no_hotspots():
    df = pd.DataFrame(columns=["position_x", "position_y", "is_functional"])

    assert find_hotspots(df) == []


def test_missing_position_columns_returns_no_hotspots():
    df = pd.DataFrame({"is_functional": [True, False]})

    assert find_hotspots(df) == []
