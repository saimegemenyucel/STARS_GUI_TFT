"""Dataclass domain models for recipes and their process steps.

These are the in-memory representation the editor manipulates. Conversion
helpers translate to/from database rows (where ``gas_mixture`` is stored as a
JSON string).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProcessStep:
    """A single ordered process step within a recipe."""

    step_order: int
    process_type: str
    process_name: str
    temperature: Optional[float] = None      # deg C
    duration: Optional[float] = None         # minutes
    gas_mixture: dict[str, float] = field(default_factory=dict)
    pressure: Optional[float] = None         # mTorr
    power: Optional[float] = None            # W
    notes: str = ""
    step_id: Optional[int] = None            # set once persisted

    def gas_mixture_json(self) -> str:
        """Serialise the gas mixture to a compact JSON string for storage."""
        return json.dumps(self.gas_mixture or {})

    @classmethod
    def from_row(cls, row) -> "ProcessStep":
        """Build a step from a sqlite3.Row / mapping."""
        return cls(
            step_id=row["step_id"],
            step_order=row["step_order"],
            process_type=row["process_type"],
            process_name=row["process_name"],
            temperature=row["temperature"],
            duration=row["duration"],
            gas_mixture=_parse_gas(row["gas_mixture"]),
            pressure=row["pressure"],
            power=row["power"],
            notes=row["notes"] or "",
        )


@dataclass
class Recipe:
    """A fabrication recipe header plus its ordered process steps."""

    recipe_name: str
    substrate_type: str
    target_process_node: str
    description: str = ""
    is_active: bool = True
    recipe_id: Optional[int] = None
    steps: list[ProcessStep] = field(default_factory=list)

    @property
    def step_count(self) -> int:
        """Number of process steps."""
        return len(self.steps)

    @property
    def estimated_duration_min(self) -> float:
        """Sum of all step durations (minutes), ignoring missing values."""
        return float(sum(s.duration or 0.0 for s in self.steps))

    def renumber_steps(self) -> None:
        """Reassign ``step_order`` to 1..N following current list order."""
        for index, step in enumerate(self.steps, start=1):
            step.step_order = index

    @classmethod
    def from_row(cls, row, steps: Optional[list[ProcessStep]] = None) -> "Recipe":
        """Build a recipe header from a sqlite3.Row / mapping."""
        return cls(
            recipe_id=row["recipe_id"],
            recipe_name=row["recipe_name"],
            substrate_type=row["substrate_type"],
            target_process_node=row["target_process_node"],
            description=row["description"] or "",
            is_active=bool(row["is_active"]),
            steps=steps or [],
        )


def _parse_gas(raw: Optional[str]) -> dict[str, float]:
    """Parse a stored gas-mixture JSON string into a dict, tolerating errors."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k): float(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Could not parse gas_mixture: %r", raw)
        return {}
