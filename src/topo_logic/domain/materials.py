"""Isotropic linear-elastic material definitions and engineering presets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.units import UnitSystem

_MPA_TO_PA = 1e6
_TONNE_PER_MM3_TO_KG_PER_M3 = 1e12


@dataclass(frozen=True)
class IsotropicMaterial:
    """Linear-elastic isotropic material parameterized in an explicit unit system."""

    name: str
    youngs_modulus: float
    poissons_ratio: float
    yield_strength: float
    density: float
    unit_system: UnitSystem = UnitSystem.MM_N_MPA

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("Material name must not be empty.")
        if not math.isfinite(self.youngs_modulus) or self.youngs_modulus <= 0.0:
            raise DomainValidationError(
                "Young's modulus must be finite and strictly positive.",
                details={"youngs_modulus": self.youngs_modulus},
            )
        if not math.isfinite(self.poissons_ratio) or not (0.0 <= self.poissons_ratio < 0.5):
            raise DomainValidationError(
                "Poisson's ratio must satisfy 0.0 <= nu < 0.5 for isotropic stability.",
                details={"poissons_ratio": self.poissons_ratio},
            )
        if not math.isfinite(self.yield_strength) or self.yield_strength <= 0.0:
            raise DomainValidationError(
                "Yield strength must be finite and strictly positive.",
                details={"yield_strength": self.yield_strength},
            )
        if not math.isfinite(self.density) or self.density <= 0.0:
            raise DomainValidationError(
                "Density must be finite and strictly positive.",
                details={"density": self.density},
            )

    def to_unit_system(self, target: UnitSystem) -> IsotropicMaterial:
        """Convert material constants cleanly between MM_N_MPA and M_N_PA."""
        if self.unit_system is target:
            return self

        if self.unit_system is UnitSystem.MM_N_MPA and target is UnitSystem.M_N_PA:
            stress_factor = _MPA_TO_PA
            density_factor = _TONNE_PER_MM3_TO_KG_PER_M3
        else:
            stress_factor = 1.0 / _MPA_TO_PA
            density_factor = 1.0 / _TONNE_PER_MM3_TO_KG_PER_M3

        return IsotropicMaterial(
            name=self.name,
            youngs_modulus=self.youngs_modulus * stress_factor,
            poissons_ratio=self.poissons_ratio,
            yield_strength=self.yield_strength * stress_factor,
            density=self.density * density_factor,
            unit_system=target,
        )


MATERIAL_PRESETS_MM: dict[str, IsotropicMaterial] = {
    "steel_aisi_1020": IsotropicMaterial(
        name="Steel AISI 1020",
        youngs_modulus=205_000.0,
        poissons_ratio=0.29,
        yield_strength=350.0,
        density=7.87e-9,
        unit_system=UnitSystem.MM_N_MPA,
    ),
    "aluminum_6061_t6": IsotropicMaterial(
        name="Aluminum 6061-T6",
        youngs_modulus=68_900.0,
        poissons_ratio=0.33,
        yield_strength=276.0,
        density=2.70e-9,
        unit_system=UnitSystem.MM_N_MPA,
    ),
    "titanium_ti6al4v": IsotropicMaterial(
        name="Titanium Ti-6Al-4V",
        youngs_modulus=113_800.0,
        poissons_ratio=0.34,
        yield_strength=880.0,
        density=4.43e-9,
        unit_system=UnitSystem.MM_N_MPA,
    ),
    "pla_generic": IsotropicMaterial(
        name="PLA (Generic FDM)",
        youngs_modulus=3_200.0,
        poissons_ratio=0.36,
        yield_strength=50.0,
        density=1.24e-9,
        unit_system=UnitSystem.MM_N_MPA,
    ),
    "petg_generic": IsotropicMaterial(
        name="PETG (Generic FDM)",
        youngs_modulus=2_100.0,
        poissons_ratio=0.38,
        yield_strength=45.0,
        density=1.27e-9,
        unit_system=UnitSystem.MM_N_MPA,
    ),
}
