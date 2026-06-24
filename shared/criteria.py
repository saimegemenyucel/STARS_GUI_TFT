"""Pass/fail evaluation of TFT measurements against quality criteria.

Both the measurement viewer (to colour devices) and the yield analyzer (to
count passes) need the same rules, so they live here in the shared layer.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def _has_value(x) -> bool:
    """True if ``x`` is a real, non-NaN value (NaN means "not measured")."""
    return x is not None and not (isinstance(x, float) and math.isnan(x))


@dataclass(frozen=True)
class QualityCriteria:
    """A bundle of active pass/fail thresholds loaded from the database.

    Any field left as ``None`` means that check is not enforced.
    """

    vth_min: Optional[float] = None
    vth_max: Optional[float] = None
    mobility_min: Optional[float] = None
    on_off_ratio_min: Optional[float] = None
    subthreshold_swing_max: Optional[float] = None
    leakage_current_max: Optional[float] = None


_PARAM_TO_FIELD = {
    "vth_min": "vth_min",
    "vth_max": "vth_max",
    "mobility_min": "mobility_min",
    "on_off_ratio_min": "on_off_ratio_min",
    "subthreshold_swing_max": "subthreshold_swing_max",
    "leakage_current_max": "leakage_current_max",
}


def load_criteria(conn: sqlite3.Connection) -> QualityCriteria:
    """Build a :class:`QualityCriteria` from the active ``quality_criteria`` rows.

    Args:
        conn: An open database connection.

    Returns:
        A populated :class:`QualityCriteria`. Parameters that are missing or
        inactive remain ``None`` (i.e. unenforced).
    """
    values: dict[str, float] = {}
    rows = conn.execute(
        "SELECT parameter_name, target_value FROM quality_criteria WHERE is_active = 1"
    ).fetchall()
    for row in rows:
        field_name = _PARAM_TO_FIELD.get(row["parameter_name"])
        if field_name is not None and row["target_value"] is not None:
            values[field_name] = float(row["target_value"])
    return QualityCriteria(**values)


def evaluate_device(measurement: dict, criteria: QualityCriteria) -> tuple[bool, dict[str, bool]]:
    """Evaluate a single measurement against the criteria.

    Args:
        measurement: Mapping with at least ``vth``, ``mobility``,
            ``on_off_ratio``, ``subthreshold_swing`` and ``leakage_current``.
        criteria: The thresholds to apply.

    Returns:
        A tuple ``(is_functional, per_parameter)`` where ``per_parameter`` maps
        each enforced check name to its boolean pass result. A device is
        functional only if every enforced check passes.
    """
    checks: dict[str, bool] = {}

    vth = measurement.get("vth")
    if _has_value(vth):
        if criteria.vth_min is not None:
            checks["vth_min"] = vth >= criteria.vth_min
        if criteria.vth_max is not None:
            checks["vth_max"] = vth <= criteria.vth_max

    mobility = measurement.get("mobility")
    if _has_value(mobility) and criteria.mobility_min is not None:
        checks["mobility_min"] = mobility >= criteria.mobility_min

    on_off = measurement.get("on_off_ratio")
    if _has_value(on_off) and criteria.on_off_ratio_min is not None:
        checks["on_off_ratio_min"] = on_off >= criteria.on_off_ratio_min

    ss = measurement.get("subthreshold_swing")
    if _has_value(ss) and criteria.subthreshold_swing_max is not None:
        checks["subthreshold_swing_max"] = ss <= criteria.subthreshold_swing_max

    leak = measurement.get("leakage_current")
    if _has_value(leak) and criteria.leakage_current_max is not None:
        checks["leakage_current_max"] = leak <= criteria.leakage_current_max

    is_functional = all(checks.values()) if checks else bool(measurement.get("is_functional"))
    return is_functional, checks
