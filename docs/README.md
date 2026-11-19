# Documentación Técnica de `Topo_Logic`

Bienvenido a la documentación interna de arquitectura, ingeniería numérica, contratos API y mantenimiento de **`Topo_Logic`**. Todo el material en `docs/` está redactado en **Español** para facilitar el diseño, la incorporación de colaboradores y el mantenimiento a largo plazo, mientras que el código fuente, `README.md`, `ROADMAP.md` y `CHANGELOG.md` siguen el estándar internacional en **Inglés**.

---

## Mapa de Documentación

| Documento | Propósito | Cuándo consultarlo |
| :--- | :--- | :--- |
| [**`arquitectura.md`**](./arquitectura.md) | Arquitectura Hexagonal, reglas de dependencia, patrones de diseño y migración Local-First → Cloud | Antes de crear módulos nuevos o refactorizar capas |
| [**`flujo-ingenieria.md`**](./flujo-ingenieria.md) | Unidades, reparación `.STL`, formulación FEM multi-loadcase, SIMP (OC/MMA + tensión P-norma) y reconstrucción | Al implementar o validar malladores, solvers u optimizadores |
| [**`contrato-api.md`**](./contrato-api.md) | Especificación REST, WebSocket y buffers binarios `Float32` para Web, CLI y Fusion 360 | Al construir clientes (Frontend Web o Add-In de Fusion 360) o endpoints |
| [**`integracion-fusion360.md`**](./integracion-fusion360.md) | Diseño del futuro Add-In de Autodesk Fusion 360 (Modo Híbrido vía API) | Al diseñar o implementar la integración de Fase 5 |
| [**`guia-mantenimiento.md`**](./guia-mantenimiento.md) | Guía práctica de entorno, tests, linters y recetas paso a paso para extender la plataforma | En el día a día de desarrollo y onboarding |

---

## Registros de Decisiones Arquitectónicas (ADRs)

Los ADRs capturan el **porqué** detrás de cada decisión estructural del sistema:

1. [**ADR-0001**](./adr/0001-arquitectura-hexagonal-python.md) — Arquitectura Hexagonal en Python 3.12+ y desacoplamiento Frontend/Backend.
2. [**ADR-0002**](./adr/0002-local-first-cloud-ready.md) — Estrategia de despliegue Local-First, Cloud-Ready.
3. [**ADR-0003**](./adr/0003-formulacion-fem-topopt-oc-mma.md) — Formulación FEM multi-loadcase y SIMP con OC, MMA (MIT) y restricción de tensión P-norma.
4. [**ADR-0004**](./adr/0004-api-agnostica-y-plugin-fusion360.md) — Contrato agnóstico de cliente (`RegionSelector`) y diseño híbrido para Fusion 360.
5. [**ADR-0005**](./adr/0005-unidades-coordenadas-e-higiene-mit.md) — Sistema consistente de unidades, guardia de escala e higiene estricta de licencia MIT.
