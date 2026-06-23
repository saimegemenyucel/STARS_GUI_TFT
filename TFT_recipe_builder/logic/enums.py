"""Enumerations for recipe process types and substrate materials."""

from __future__ import annotations

from enum import Enum


class ProcessType(str, Enum):
    """Category of a fabrication process step."""

    DEPOSITION = "deposition"
    LITHOGRAPHY = "lithography"
    ETCHING = "etching"
    ANNEALING = "annealing"
    CLEANING = "cleaning"

    @classmethod
    def values(cls) -> list[str]:
        """Return all process-type string values in declaration order."""
        return [member.value for member in cls]


class SubstrateType(str, Enum):
    """Supported substrate materials."""

    GLASS = "glass"
    PLASTIC = "plastic"
    SILICON = "silicon"

    @classmethod
    def values(cls) -> list[str]:
        """Return all substrate-type string values in declaration order."""
        return [member.value for member in cls]
