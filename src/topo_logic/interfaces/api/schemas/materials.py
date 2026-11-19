"""Pydantic schemas for engineering material library endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from topo_logic.domain.materials import IsotropicMaterial
from topo_logic.domain.units import UnitSystem


class MaterialPresetResponse(BaseModel):
    """Serialized isotropic material preset in the requested consistent unit system."""

    id: str
    name: str
    youngs_modulus: float
    poissons_ratio: float
    yield_strength: float
    density: float
    unit_system: UnitSystem
    stress_unit: str
    density_unit: str
    density_kg_m3: float

    @classmethod
    def from_domain(cls, preset_id: str, material: IsotropicMaterial) -> MaterialPresetResponse:
        stress_unit = "MPa" if material.unit_system is UnitSystem.MM_N_MPA else "Pa"
        density_unit = "tonne/mm^3" if material.unit_system is UnitSystem.MM_N_MPA else "kg/m^3"
        density_kg_m3 = material.to_unit_system(UnitSystem.M_N_PA).density
        return cls(
            id=preset_id,
            name=material.name,
            youngs_modulus=material.youngs_modulus,
            poissons_ratio=material.poissons_ratio,
            yield_strength=material.yield_strength,
            density=material.density,
            unit_system=material.unit_system,
            stress_unit=stress_unit,
            density_unit=density_unit,
            density_kg_m3=density_kg_m3,
        )
