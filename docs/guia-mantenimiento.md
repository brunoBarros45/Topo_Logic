# Guía de Mantenimiento y Extensión

Manual operativo para desarrolladores y mantenedores de `Topo_Logic`.

---

## 1. Configuración del Entorno Local

Requiere **Python 3.11+** (probado en Python 3.12 en Windows).

```powershell
# 1. Crear entorno virtual aislado
python3.12 -m venv .venv

# 2. Instalar en modo editable junto a herramientas de desarrollo
.\.venv\Scripts\pip.exe install -e ".[dev]"

# 3. Verificar instalación CLI
.\.venv\Scripts\topo-logic.exe info
```

Para instalar dependencias adicionales de optimización/FEM avanzado (Fases 2–3):

```powershell
.\.venv\Scripts\pip.exe install -e ".[topopt,dev]"
```

---

## 2. Verificación Antes de Cada Commit

```powershell
# Suite completa (fronteras AST, dominio, pipeline STL e integración API)
.\.venv\Scripts\pytest.exe -v

# Chequeo estático estricto de tipos
.\.venv\Scripts\mypy.exe src/topo_logic

# Linter y formato de código
.\.venv\Scripts\ruff.exe check src tests
```

> **Regla crítica:** Nunca edites ni formatees archivos dentro de `references/` (es una biblioteca local de solo lectura excluida de Git).

---

## 3. Recetas Paso a Paso para Extender la Plataforma

### 3.1. Cómo agregar un nuevo formato 3D (`.OBJ`, `.PLY`, `.STEP`)
1. Crea un adaptador en `src/topo_logic/infrastructure/mesh/` que implemente `GeometryImporterPort` (métodos `supported_formats()` y `extract_surface_stl()`), o extiende un importador compuesto (*Composite Strategy*).
2. Conéctalo en `build_container()` dentro de [`src/topo_logic/interfaces/api/dependencies.py`](../src/topo_logic/interfaces/api/dependencies.py).
3. Añade pruebas unitarias e integración en `tests/` verificando unidades, orientación y manejo de errores.
4. No necesitas modificar `IngestGeometryUseCase` ni los routers HTTP.

### 3.2. Cómo agregar un nuevo Solver Lineal o Estrategia de Optimización
1. Define o reutiliza el puerto correspondiente en `src/topo_logic/application/ports/simulation.py` (`LinearSystemSolverPort`, `OptimizerPort`).
2. Implementa el adaptador concreto bajo `src/topo_logic/infrastructure/`.
3. Verifica estrictamente que las dependencias empleadas sean **MIT / BSD / Apache-2.0** (ver [ADR-0005](./adr/0005-unidades-coordenadas-e-higiene-mit.md)).
4. Agrega un benchmark analítico con marca `@pytest.mark.benchmark` (por ejemplo, *patch test* o viga en voladizo) antes de integrarlo en la API.

### 3.3. Cómo migrar a almacenamiento/cola Cloud (PostgreSQL + S3 + Redis)
1. Implementa `Postgres*Repository`, `S3ArtifactStorage`, `CeleryJobQueue` y `RedisPubSubEventBus` bajo `src/topo_logic/infrastructure/`.
2. Selecciona los adaptadores en `build_container(settings)` según la configuración de entorno (`AppSettings`).
3. El dominio (`domain/`), los casos de uso (`application/`) y los contratos de API (`interfaces/`) permanecen intactos.

---

## 4. Convenciones de Código y Calidad

- **Docstrings y comentarios:** escritos en Inglés claro y conciso; documenta el *porqué* en lógica numérica no obvia.
- **Tipado estricto:** `mypy --strict` debe pasar con cero errores. Evita `Any` y `# type: ignore` salvo causa justificada.
- **Inmutabilidad en Dominio:** entidades y value objects son `@dataclass(frozen=True)` con validación en `__post_init__`.
- **Control de versiones:** actualiza la tabla de progreso en `README.md`, `ROADMAP.md` y `CHANGELOG.md` al completar cada hito.
