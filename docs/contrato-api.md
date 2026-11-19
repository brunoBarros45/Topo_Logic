# Contrato de API Agnóstico de Cliente (`REST + WebSocket + Binary`)

La API HTTP/WebSocket de `Topo_Logic` es la frontera oficial consumida por el futuro **Frontend Web**, el **CLI** y el futuro **Add-In de Autodesk Fusion 360**.

---

## 1. Endpoints Implementados (Fases 1 y 2 Operativas)

### 1.1. Salud y Descubrimiento de Capacidades
- `GET /api/v1/health`
  - Respuesta `200 OK`:
    ```json
    {
      "status": "ok",
      "version": "0.2.0a0",
      "execution_mode": "local_first",
      "supported_formats": ["stl"]
    }
    ```
  - Uso clave: tanto el Frontend Web como el Add-In de Fusion 360 consultan este endpoint al arrancar para verificar conectividad y qué formatos 3D acepta el servidor.

### 1.2. Catálogo de Materiales Isotrópicos
- `GET /api/v1/materials?unit_system=mm_N_MPa|m_N_Pa` (`200 OK`) — Lista los presets de ingeniería (`steel_aisi_1020`, `aluminum_6061_t6`, `titanium_ti6al4v`, `pla_generic`, `petg_generic`) convertidos automáticamente al sistema de unidades solicitado (`stress_unit`, `density_unit` y referencia `density_kg_m3`).
- `GET /api/v1/materials/{material_id}?unit_system=mm_N_MPa|m_N_Pa` (`200 OK` | `404 ErrorEnvelope`)

### 1.3. Proyectos
- `POST /api/v1/projects` (`201 Created`) — `{ "name": "...", "description": "..." }`
- `GET /api/v1/projects` (`200 OK`)
- `GET /api/v1/projects/{project_id}` (`200 OK`)

### 1.4. Ingesta, Diagnóstico y Descarga de Geometría `.STL`
- `POST /api/v1/projects/{project_id}/geometries/upload` (`201 Created`, `multipart/form-data`)
  - Campos form:
    - `file`: archivo `.stl` (binario o ASCII)
    - `unit_system`: `"mm_N_MPa"` *(default)* | `"m_N_Pa"`
    - `axis_convention`: `"Z_up"` *(default)* | `"Y_up"`
    - `auto_repair`: `true` *(default)* | `false`
  - Devuelve `GeometryAssetResponse` con métricas (`vertex_count`, `triangle_count`, `is_watertight`, `boundary_edge_count`, `non_manifold_edge_count`, `volume`, `surface_area`, `bounds`), `scale_guard` y `repair_report`.
- `GET /api/v1/projects/{project_id}/geometries` (`200 OK`)
- `GET /api/v1/geometries/{geometry_id}` (`200 OK`)
- `GET /api/v1/geometries/{geometry_id}/download?variant=repaired|raw` (`200 OK`, `application/octet-stream`)

### 1.5. Mallado Volumétrico y Superficie de Picking (Fase 2)
- `POST /api/v1/projects/{project_id}/meshes` (`201 Created`) — `{ "geometry_id": "...", "element_type": "H8"|"C3D4"|"C3D10", "target_element_size": 5.0 }`
- `GET /api/v1/projects/{project_id}/meshes` (`200 OK`)
- `GET /api/v1/meshes/{mesh_id}` (`200 OK`)
- `GET /api/v1/meshes/{mesh_id}/surface` (`200 OK`) — Devuelve vértices `nodes` y triángulos exteriores `surface_triangles` indexados 1:1 a los nodos volumétricos.

### 1.6. Estudios FEM Estáticos Multi-Loadcase y Campos Binarios `Float32` (Fase 2)
- `POST /api/v1/projects/{project_id}/studies/fem` (`202 Accepted` -> `JobResponse`) — Recibe `geometry_id`, `mesh_id`, `unit_system`, `material` (`preset_id` o constantes propias), `regions` (`plane`, `bounding_box`, `triangle_set`, `cad_face_tag`), `supports` y `load_cases[]` (`force`, `pressure`).
- `GET /api/v1/jobs/{job_id}/fem-summary` (`200 OK`) — Devuelve `FemResultSummaryResponse` con compliance, rangos de desplazamiento/Von Mises, factor de seguridad mínimo y chequeo de equilibrio estático por caso de carga.
- `GET /api/v1/jobs/{job_id}/fields/{load_case_id}?field=displacement|displacement_magnitude|von_mises|safety_factor` (`200 OK`, `application/octet-stream`) — Devuelve buffer binario little-endian `Float32` con headers `X-Topo-Dtype`, `X-Topo-Shape`, `X-Topo-Unit`, `X-Topo-Min`, `X-Topo-Max`.

### 1.7. Jobs y Cancelación Cooperativa
- `GET /api/v1/projects/{project_id}/jobs` (`200 OK`)
- `GET /api/v1/jobs/{job_id}` (`200 OK`)
- `POST /api/v1/jobs/{job_id}/cancel` (`200 OK`)

### 1.8. Streaming en Tiempo Real (`WebSocket`)
- `WS /ws/jobs/{job_id}`
  - Al conectarse envía inmediatamente un frame `job.snapshot` con el estado actual del trabajo.
  - Emite eventos incrementales conforme avanzan las etapas (`job.meshing`, `job.solving`, `job.optimizing`, `topopt.iteration`, `job.completed`, `job.cancelled`, `job.failed`).
  - Formato de frame de control JSON:
    ```json
    {
      "event_type": "job.optimizing",
      "job_id": "uuid",
      "status": "optimizing",
      "progress": 0.45,
      "message": "Iteration 36/80",
      "payload": {
        "iteration": 36,
        "compliance": 12.48,
        "volume_fraction": 0.301,
        "max_density_change": 0.018
      }
    }
    ```

---

## 2. Formato Estándar de Errores (`ErrorEnvelope`)

Todas las excepciones de dominio se mapean automáticamente a HTTP limpio (`404`, `409`, `413`, `415`, `422`, `400`):

```json
{
  "code": "unsupported_format",
  "message": "Format '.obj' is not enabled yet in this phase. Currently supported formats: ['stl'].",
  "details": {
    "format": "obj",
    "supported_formats": ["stl"]
  }
}
```

---

## 3. Contratos Planificados para Fase 3 (`[Fase 3]`)

- `[Fase 3]` `POST /api/v1/projects/{project_id}/studies/topopt` — Lanza optimización SIMP (`OC` o `MMA` con restricción P-norma opcional) y zonas pasivas sólidas/vacías.
- `[Fase 3]` `GET /api/v1/jobs/{job_id}/reconstructed-stl` — Descarga el `.STL` *watertight* suavizado con Taubin resultante.
