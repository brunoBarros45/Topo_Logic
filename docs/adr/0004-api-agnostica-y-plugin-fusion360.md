# ADR-0004: API Agnóstica de Cliente (`RegionSelector`) y Plugin Híbrido para Fusion 360

- **Estado:** Aceptado
- **Fecha:** 2026-11-18

## Contexto
El backend servirá tanto a un Frontend Web basado en Three.js (sobre triángulos de malla `.STL`/`.OBJ`), como a scripts CLI/benchmarks y a un futuro Add-In de **Autodesk Fusion 360** (que trabaja nativamente con caras B-Rep).

## Decisión
1. Representar las regiones de condiciones de contorno (`BoundaryRegion`) mediante una unión discriminada agnóstica de cliente (`TriangleSetSelector`, `PlaneSelector`, `BoundingBoxSelector`, `CadFaceTagSelector`) en lugar de asumir índices de triángulos.
2. Diseñar el futuro Add-In de Fusion 360 en **Modo Híbrido vía API** (cliente ligero Python `adsk.core`/`adsk.fusion` comunicándose por HTTP/WebSocket con `topo-logic serve` local o remoto) en lugar de importar `SciPy`/`NumPy`/`trimesh` dentro del intérprete Python embebido de Fusion.

## Alternativas Consideradas
- **Embeber todo el motor dentro del Python de Fusion 360:** Propenso a fallos por versiones fijas de Python/C-extensions de Autodesk y bloqueo de la interfaz CAD.
- **Solo cliente hacia servidor cloud:** Impediría usar el plugin offline en estaciones de trabajo locales.

## Consecuencias
- **Positivas:** Aislamiento total de dependencias en Fusion 360, soporte offline y remoto con el mismo código, y cero duplicación de lógica FEM/TopOpt.
- **Negativas / Mitigación:** El Add-In requiere verificar o levantar el proceso `topo-logic serve` en local (`GET /api/v1/health`); la Fase 1 ya entrega dicho CLI y endpoint.
