"""Isotropic engineering material preset endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from topo_logic.domain.exceptions import ResourceNotFoundError
from topo_logic.domain.materials import MATERIAL_PRESETS_MM
from topo_logic.domain.units import UnitSystem
from topo_logic.interfaces.api.schemas import MaterialPresetResponse

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("", response_model=list[MaterialPresetResponse])
def list_materials(unit_system: UnitSystem = UnitSystem.MM_N_MPA) -> list[MaterialPresetResponse]:
    """Return all built-in isotropic material presets converted to the target unit system."""
    return [
        MaterialPresetResponse.from_domain(preset_id, material.to_unit_system(unit_system))
        for preset_id, material in MATERIAL_PRESETS_MM.items()
    ]


@router.get("/{material_id}", response_model=MaterialPresetResponse)
def get_material(
    material_id: str,
    unit_system: UnitSystem = UnitSystem.MM_N_MPA,
) -> MaterialPresetResponse:
    """Return a single built-in material preset by ID."""
    material = MATERIAL_PRESETS_MM.get(material_id)
    if material is None:
        raise ResourceNotFoundError(
            f"Material preset '{material_id}' was not found.",
            details={"material_id": material_id},
        )
    return MaterialPresetResponse.from_domain(material_id, material.to_unit_system(unit_system))
