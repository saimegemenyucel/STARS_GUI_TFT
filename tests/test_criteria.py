"""Tests for shared.criteria pass/fail evaluation."""

from __future__ import annotations

import math

from shared.criteria import QualityCriteria, evaluate_device


def test_device_passes_when_all_enforced_checks_pass():
    criteria = QualityCriteria(vth_min=-1.0, vth_max=1.0, mobility_min=5.0)
    measurement = {"vth": 0.5, "mobility": 10.0}

    is_functional, checks = evaluate_device(measurement, criteria)

    assert is_functional is True
    assert checks == {"vth_min": True, "vth_max": True, "mobility_min": True}


def test_device_fails_when_any_enforced_check_fails():
    criteria = QualityCriteria(mobility_min=5.0)
    measurement = {"mobility": 1.0}

    is_functional, checks = evaluate_device(measurement, criteria)

    assert is_functional is False
    assert checks == {"mobility_min": False}


def test_unset_criteria_are_not_enforced():
    criteria = QualityCriteria()  # nothing active
    measurement = {"vth": 99.0, "mobility": -5.0}

    is_functional, checks = evaluate_device(measurement, criteria)

    assert checks == {}
    # Falls back to the stored is_functional flag when no checks apply.
    assert is_functional is False


def test_missing_measurement_field_skips_that_check():
    criteria = QualityCriteria(vth_min=-1.0, mobility_min=5.0)
    measurement = {"mobility": 10.0}  # no vth present

    is_functional, checks = evaluate_device(measurement, criteria)

    assert "vth_min" not in checks
    assert checks["mobility_min"] is True
    assert is_functional is True


def test_nan_measurement_field_is_treated_as_missing_not_a_failure():
    """A NaN (e.g. an uncomputed leakage_current) must be skipped like a
    missing field, not silently fail the device. Regression: NaN passed
    `is not None`, so every device failed a check it had no data for.
    """
    criteria = QualityCriteria(mobility_min=5.0, leakage_current_max=1e-9)
    measurement = {"mobility": 10.0, "leakage_current": math.nan}

    is_functional, checks = evaluate_device(measurement, criteria)

    assert "leakage_current_max" not in checks
    assert checks["mobility_min"] is True
    assert is_functional is True
