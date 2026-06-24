"""Tests for shared.tft_analysis, including the mu_sat noise-blowup fix.

A "dead" transistor whose current never rises above the measurement noise
floor must not produce a fitted mobility: squaring a noise-driven slope used
to report mobilities in the billions of cm^2/Vs (see git history). The fix
in ``_sqrt_extrapolation`` should reject those fits as NaN instead.
"""

from __future__ import annotations

import numpy as np

from shared.tft_analysis import (
    MAX_PHYSICAL_MU_SAT_CM2VS,
    TransferCurve,
    average_mobility,
    extract_transfer_features,
    oxide_capacitance_per_area,
)

W_UM, L_UM = 10.0, 5.0


def _flat_noise_curve(seed: int) -> TransferCurve:
    """A device that never turns on: Id pinned near the noise floor."""
    rng = np.random.default_rng(seed)
    vg = np.linspace(-5, 5, 41)
    floor = 1e-13
    idd = floor * (1 + rng.normal(0, 0.015, vg.size))
    idd = np.clip(idd, floor * 0.5, None)
    gate_i = rng.normal(0, 1e-12, vg.size)
    return TransferCurve(gate_v=vg, drain_i=-idd, gate_i=gate_i, drain_v=-5.0)


def _real_turn_on_curve() -> TransferCurve:
    """A device with a clean square-law turn-on (vth=0V, mu=15 cm^2/Vs)."""
    vg = np.linspace(-5, 5, 41)
    vth, mu = 0.0, 15.0
    cox = 8.8541878128e-14 * 8.0 / (25.0 * 1e-7)
    w_cm, l_cm = W_UM * 1e-4, L_UM * 1e-4
    k = 0.5 * (w_cm / l_cm) * mu * cox
    vov = np.clip(vg - vth, 0, None)
    idd = k * vov ** 2 + 1e-13
    return TransferCurve(gate_v=vg, drain_i=-idd, gate_i=np.zeros_like(vg), drain_v=-5.0)


def test_dead_device_does_not_produce_unphysical_mobility():
    for seed in range(20):
        curve = _flat_noise_curve(seed)
        features = extract_transfer_features(curve, w_um=W_UM, l_um=L_UM)
        assert not (features.mu_sat > MAX_PHYSICAL_MU_SAT_CM2VS)


def test_functioning_device_still_recovers_mobility():
    curve = _real_turn_on_curve()
    features = extract_transfer_features(curve, w_um=W_UM, l_um=L_UM)

    assert np.isfinite(features.mu_sat)
    assert 5.0 < features.mu_sat < 30.0  # recovers ~15 cm^2/Vs within tolerance
    assert abs(features.vth_sat) < 1.0  # recovers ~0 V within tolerance


def test_average_mobility_rejects_near_singularity_spikes():
    """mu_AVG = Id*L / (W*Cox*overdrive*vch) blows up near overdrive=0 or
    vch=0. A non-zero contact resistance (rc_ohm) makes vch data-dependent, so
    the crossing point isn't predictable from vg alone -- the old `abs(x) >
    1e-9` guard let huge-but-finite values through whenever the crossing fell
    a few hundred mV away rather than literally at it.
    """
    vg = np.linspace(-5, 5, 41)
    vth, vd = 1.0, -5.0
    cox = oxide_capacitance_per_area(25.0, 8.0)
    w_um, l_um = 10.0, 5.0
    w_cm, l_cm = w_um * 1e-4, l_um * 1e-4
    k = (w_cm / l_cm) * 100.0 * cox  # mu=100 cm^2/Vs, deliberately large
    vov = np.clip(vg - vth, 0, None)
    idd = -k * (vov * abs(vd) - abs(vd) ** 2 / 2.0)

    mu_avg, _ = average_mobility(vg, idd, vth, vd, w_um, l_um, cox, rc_ohm=5000.0)

    finite = mu_avg[np.isfinite(mu_avg)]
    assert finite.size > 0
    assert np.all(np.abs(finite) <= MAX_PHYSICAL_MU_SAT_CM2VS)
