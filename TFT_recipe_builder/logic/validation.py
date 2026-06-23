"""Validation rules for recipes and process steps."""

from __future__ import annotations

import logging

from TFT_recipe_builder.logic.enums import ProcessType, SubstrateType
from TFT_recipe_builder.logic.models import ProcessStep, Recipe

logger = logging.getLogger(__name__)

# Plausible temperature window (deg C) per process type, used to warn the user.
TEMPERATURE_LIMITS: dict[str, tuple[float, float]] = {
    ProcessType.DEPOSITION.value: (20.0, 600.0),
    ProcessType.LITHOGRAPHY.value: (20.0, 200.0),
    ProcessType.ETCHING.value: (-20.0, 400.0),
    ProcessType.ANNEALING.value: (100.0, 900.0),
    ProcessType.CLEANING.value: (15.0, 150.0),
}


def validate_step(step: ProcessStep) -> list[str]:
    """Validate a single process step.

    Args:
        step: The step to check.

    Returns:
        A list of human-readable error messages; empty if the step is valid.
    """
    errors: list[str] = []

    if not step.process_name or not step.process_name.strip():
        errors.append("Process name is required.")
    if step.process_type not in ProcessType.values():
        errors.append(f"Unknown process type: {step.process_type!r}.")

    if step.duration is not None and step.duration <= 0:
        errors.append("Duration must be greater than 0 minutes.")
    if step.pressure is not None and step.pressure < 0:
        errors.append("Pressure cannot be negative.")
    if step.power is not None and step.power < 0:
        errors.append("Power cannot be negative.")

    limits = TEMPERATURE_LIMITS.get(step.process_type)
    if step.temperature is not None and limits is not None:
        lo, hi = limits
        if not (lo <= step.temperature <= hi):
            errors.append(
                f"Temperature {step.temperature}°C is outside the typical "
                f"{step.process_type} range [{lo}, {hi}]°C."
            )

    for gas, frac in (step.gas_mixture or {}).items():
        if frac < 0:
            errors.append(f"Gas fraction for {gas} cannot be negative.")
    return errors


def validate_recipe(recipe: Recipe) -> list[str]:
    """Validate a whole recipe, aggregating per-step errors.

    Args:
        recipe: The recipe to check.

    Returns:
        A list of error messages; empty if the recipe is valid.
    """
    errors: list[str] = []
    if not recipe.recipe_name or not recipe.recipe_name.strip():
        errors.append("Recipe name is required.")
    if recipe.substrate_type not in SubstrateType.values():
        errors.append(f"Unknown substrate type: {recipe.substrate_type!r}.")
    if not recipe.steps:
        errors.append("A recipe must contain at least one process step.")

    for step in recipe.steps:
        for msg in validate_step(step):
            errors.append(f"Step {step.step_order}: {msg}")
    return errors
