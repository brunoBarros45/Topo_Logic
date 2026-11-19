"""Consistent physical unit systems, axis conventions, and scale-sanity guards."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from topo_logic.domain.exceptions import DomainValidationError


class UnitSystem(StrEnum):
    """Supported consistent engineering unit systems."""

    MM_N_MPA = "mm_N_MPa"
    M_N_PA = "m_N_Pa"


class AxisConvention(StrEnum):
    """Explicit right-handed up-axis convention tagged on ingested geometries."""

    Z_UP = "Z_up"
    Y_UP = "Y_up"


@dataclass(frozen=True)
class ScaleGuardWarning:
    """Result of evaluating bounding-box scale consistency against a chosen unit system."""

    is_suspicious: bool
    suggested_scale_factor: float | None = None
    suggested_unit_system: UnitSystem | None = None
    message: str | None = None


def evaluate_scale_guard(bbox_diagonal: float, unit_system: UnitSystem) -> ScaleGuardWarning:
    """Detect common CAD STL/OBJ unit mismatches (mm exported into m or vice versa)."""
    if not math.isfinite(bbox_diagonal) or bbox_diagonal <= 0.0:
        raise DomainValidationError(
            "Bounding-box diagonal must be a finite positive number.",
            details={"bbox_diagonal": bbox_diagonal},
        )

    if unit_system is UnitSystem.M_N_PA and bbox_diagonal > 20.0:
        return ScaleGuardWarning(
            is_suspicious=True,
            suggested_scale_factor=0.001,
            suggested_unit_system=UnitSystem.MM_N_MPA,
            message=(
                f"Bounding-box diagonal is {bbox_diagonal:.3g} under meters (m_N_Pa). "
                "The file may be authored in millimeters; consider switching to mm_N_MPa "
                "or scaling by 0.001."
            ),
        )

    if unit_system is UnitSystem.MM_N_MPA and bbox_diagonal < 1.0:
        return ScaleGuardWarning(
            is_suspicious=True,
            suggested_scale_factor=1000.0,
            suggested_unit_system=UnitSystem.M_N_PA,
            message=(
                f"Bounding-box diagonal is {bbox_diagonal:.3g} under millimeters (mm_N_MPa). "
                "The file may be authored in meters; consider switching to m_N_Pa "
                "or scaling by 1000."
            ),
        )

    return ScaleGuardWarning(is_suspicious=False)
