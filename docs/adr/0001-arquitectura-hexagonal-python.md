# ADR-0001: Arquitectura Hexagonal en Python 3.12+ y Backend/Frontend Desacoplados

- **Estado:** Aceptado
- **Fecha:** 2026-11-18

## Contexto
`Topo_Logic` debe resolver análisis por Elementos Finitos (FEM) 3D y Optimización Topológica sobre modelos 3D cargados por el usuario, sirviendo inicialmente a una futura aplicación web y, en una fase posterior, a un Add-In de Autodesk Fusion 360. Además, el stack del frontend web se definirá en una fase posterior.

## Decisión
1. Adoptar **Python 3.11+ (desarrollo en 3.12)** para el motor numérico y el backend API (**FastAPI + Pydantic v2**), apoyándose en librerías compiladas con licencia MIT/BSD (`NumPy`, `SciPy`, `trimesh`, `scikit-fem`, `pyamg`, `scikit-image`).
2. Estructurar el paquete bajo **Arquitectura Limpia / Hexagonal** en cuatro capas estrictas (`domain`, `application`, `infrastructure`, `interfaces`), verificadas automáticamente mediante un test de fronteras AST.
3. Mantener cualquier cliente gráfico (Frontend Web futuro, CLI, Fusion 360) completamente fuera del núcleo, comunicándose exclusivamente vía OpenAPI REST, WebSocket y buffers binarios `Float32`.

## Alternativas Consideradas
- **Motor en navegador (WebAssembly / JS puro):** Descartado por limitaciones severas de memoria/BLAS para sistemas dispersos 3D y por imposibilitar reutilizar el mismo motor en workflows de Fusion 360.
- **Monolito acoplado Next.js/Python sin capas:** Descartado porque dificultaría reemplazar algoritmos, hacer benchmarks unitarios sin HTTP o añadir clientes nativos CAD.

## Consecuencias
- **Positivas:** Máxima velocidad de desarrollo numérico con ecosistema MIT/BSD maduro; 100% reutilizable entre Web, CLI y Fusion 360; permite diferir la elección del Frontend sin coste de retrabajo.
- **Negativas / Mitigación:** Exige disciplina de fronteras entre capas (mitigado con `test_architecture_boundaries.py` y `mypy --strict`).
