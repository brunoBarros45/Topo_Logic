# ADR-0003: Formulación FEM Multi-Loadcase y TopOpt SIMP con OC, MMA y Tensión P-Norma

- **Estado:** Aceptado
- **Fecha:** 2026-11-18

## Contexto
Las piezas mecánicas reales rara vez operan bajo un único caso de carga o sin límites de tensión admisible. Aunque **Optimality Criteria (OC)** es rápido e ideal para minimizar compliance bajo restricción única de volumen, no admite múltiples restricciones como límites de tensión de Von Mises o desplazamiento.

## Decisión
1. Modelar **múltiples casos de carga (`LoadCase[]`)** desde la Fase 1 en el dominio (`FemStudyConfig`), permitiendo tanto estudios FEM independientes por caso como optimización ponderada multi-loadcase.
2. Soportar dos estrategias tras `OptimizerPort`:
   - **`OC` (Optimality Criteria):** Por defecto para optimización rápida de rigidez con restricción única de volumen.
   - **`MMA` (Method of Moving Asymptotes, adaptado de `pyMOTO` con licencia MIT):** Habilita restricciones adicionales como **tensión máxima de Von Mises agregada vía P-norma** (`StressConstraintConfig`).
3. Validar en el propio dominio (`TopOptStudyConfig`) que activar restricciones de tensión con `OptimizerKind.OC` produzca un error inmediato de validación.

## Alternativas Consideradas
- **Solo OC en v1 y refactorizar luego:** Obligaría a cambiar todos los contratos de estudio, API y serialización en fases posteriores.
- **Usar `mmapy` (`TopOpt-MMA-Python`):** Descartado terminantemente porque `mmapy` tiene licencia **GPL-3.0**, incompatible con `Topo_Logic` (MIT).

## Consecuencias
- **Positivas:** El contrato de dominio y API nace preparado para ingeniería estructural real y multi-restricción sin deuda técnica futura.
- **Negativas / Mitigación:** Mayor riqueza en los esquemas de configuración; mitigado mediante valores por defecto sensatos (`OC` + un `LoadCase` + `StressConstraintConfig(enabled=False)`).
