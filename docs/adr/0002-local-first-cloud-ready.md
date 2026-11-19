# ADR-0002: Estrategia Local-First, Cloud-Ready

- **Estado:** Aceptado
- **Fecha:** 2026-11-18

## Contexto
Durante las primeras fases del proyecto y en uso individual de ingeniería (incluido el modo local del futuro plugin de Fusion 360), la aplicación debe arrancar con cero infraestructura externa (sin requerir Docker, PostgreSQL, Redis ni S3 instalados). Sin embargo, el proyecto debe poder escalar a un despliegue multiusuario en la nube en el futuro.

## Decisión
Implementar un modo **Local-First** por defecto detrás de puertos `typing.Protocol` en `src/topo_logic/application/ports/`:
- Almacenamiento de artefactos: `LocalFsArtifactStorage` (escritura atómica en `.topo_logic_data/artifacts/`).
- Metadatos: `SqliteDatabase` en modo WAL (`.topo_logic_data/topo_logic.db`).
- Cola de trabajos y eventos: `LocalJobQueue` + `InMemoryEventBus` con `ThreadingCancellationToken`.

## Alternativas Consideradas
- **Solo scripts en memoria sin base de datos ni cola:** Impediría cancelar trabajos, auditar historiales o escalar a la nube.
- **Exigir PostgreSQL + Redis + MinIO desde el Día 1:** Frena innecesariamente las pruebas locales y complica el uso en escritorio/Fusion 360.

## Consecuencias
- **Positivas:** Experiencia de arranque instantáneo con `topo-logic serve` y migración limpia a S3/PostgreSQL/Redis en Fase 5 cambiando únicamente los adaptadores en `dependencies.py`.
- **Negativas / Mitigación:** En SQLite local no se permite concurrencia distribuida entre múltiples máquinas; queda resuelto al activar los adaptadores Cloud.
