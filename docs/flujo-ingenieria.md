# Flujo de Ingeniería y Formulación Numérica

Este documento describe el pipeline completo de ingeniería de `Topo_Logic`, desde la carga de archivos 3D hasta el análisis FEM multi-loadcase y la optimización topológica 3D.

---

## 1. Sistema Consistente de Unidades y Convención de Ejes

Los formatos `.STL` y `.OBJ` no transportan metadatos estándar de unidades. Para evitar errores de rigidez de $10^9\times$, el dominio exige declarar explícitamente el sistema de unidades antes de mallar o resolver (`src/topo_logic/domain/units.py`):

| Magnitud Física | `mm_N_MPa` (Ingeniería CAD, por defecto) | `m_N_Pa` (SI Estándar) |
| :--- | :--- | :--- |
| Longitud | `mm` | `m` |
| Fuerza | `N` | `N` |
| Tensión / Módulo de Young ($E$) | `MPa` ($\text{N/mm}^2$) | `Pa` ($\text{N/m}^2$) |
| Densidad ($\rho$) | `tonne/mm³` ($10^{-12}\text{ kg/mm}^3$, p. ej. acero $= 7.87 \times 10^{-9}$) | `kg/m³` (p. ej. acero $= 7870$) |

### Guardia de Escala Sospechosa (`evaluate_scale_guard`)
Al ingerir una geometría se calcula la diagonal $D$ de la caja envolvente:
- Si el usuario eligió **`m_N_Pa`** y $D > 20$: es altamente probable que el archivo esté en milímetros. Se emite `ScaleGuardWarning` sugiriendo `mm_N_MPa` o factor `0.001`.
- Si el usuario eligió **`mm_N_MPa`** y $D < 1$: es probable que el archivo esté en metros. Se sugiere `m_N_Pa` o factor `1000.0`.

### Convención de Ejes
Toda geometría se etiqueta explícitamente con sistema dextrógiro `Z_up` (estándar CAD: Fusion 360, FreeCAD, SolidWorks) o `Y_up` (estándar web/Three.js), preservando las coordenadas originales del modelo sin mutaciones silenciosas.

---

## 2. Pipeline de Ingesta y Reparación `.STL` (Fase 1 Operativa)

Implementado en `TrimeshStlImporter` y `TrimeshSurfaceRepairer`:

1. **Carga sin procesamiento previo** (`process=False`): permite medir con precisión vértices duplicados y triángulos degenerados del archivo original (en STL binario/ASCII sin indexar, cada triángulo trae 3 vértices separados).
2. **Validación estructural**: rechaza archivos vacíos, corruptos, sin caras o con coordenadas no finitas (`NaN`/`Inf`).
3. **Escalera de Reparación Tier-1 (`auto_repair=True`)**:
   - Fusión de vértices duplicados dentro de tolerancia relativa $\text{tol} = \max(10^{-9}, 10^{-6} \cdot D)$.
   - Eliminación de caras degeneradas (área cero) y caras duplicadas.
   - Intento de cierre de huecos menores (`fill_holes`).
   - Corrección de *winding* y normales hacia el exterior (`fix_winding`, `fix_normals` e inversión si volumen cerrado $< 0$).
4. **Auditoría Topológica**:
   - Cuenta aristas de borde libre ($\text{grado} = 1$), aristas no-variedad ($\text{grado} > 2$) y componentes conectados.
   - Verifica `is_watertight`, volumen encerrado, área superficial y ejecuta la guardia de escala.
   - Exporta `.STL` binario canónico reparado y conserva el archivo original intacto.

---

## 3. Análisis FEM Estático Lineal 3D (Multi-Loadcase — Fase 2 Operativa)

### 3.1. Discretización Volumétrica (`VolumetricMesherPort`)
- **Elementos hexaédricos `H8` voxelizados (`VoxelH8Mesher`, 100% MIT):** ray-casting de paridad en columnas Z proyectadas sobre NumPy puro (sin requerir `rtree`), ideal para optimización topológica rápida compartiendo una matriz elemental de referencia $\mathbf{K}_0$ de $24 \times 24$.
- **Elementos tetraédricos `C3D4` / cuadráticos `C3D10` vía `GmshCliMesher` (opcional):** subproceso externo contra el binario CLI de Gmsh (MSH v2.2 con remapeo de nodos cuadráticos 8/9 al orden canónico).

### 3.2. Elasticidad Lineal y Condiciones de Contorno
Para material isotrópico $(E > 0,\, 0 \le \nu < 0.5)$ con matriz constitutiva $\mathbf{D}_{6\times 6}$ en notación de Voigt `[xx, yy, zz, yz, xz, xy]`:
- **Dirichlet (`extract_dirichlet_dofs`):** validación automática de restricciones sobre los 3 ejes traslacionales ($\ge 6$ DOFs) y eliminación simétrica manteniendo $\mathbf{K}_{ff}$ simétrica definida positiva (SPD).
- **Neumann (`ForceLoad` / `PressureLoad`):** integración consistente por cara según el tipo de elemento: $\frac{1}{4} A_q$ por vértice en caras cuadriláteras `Q4` de mallas `H8`, $(0,0,0,\frac{1}{3},\frac{1}{3},\frac{1}{3}) A_f$ en caras cuadráticas `T6` de mallas `C3D10` y $\frac{1}{3} A_f$ en triángulos lineales `T3`.
- **Multi-Loadcase:** `solve_reduced_systems` factoriza una sola vez con `splu` (`< 80k` DOFs) o precondiciona con `pyamg` Smoothed Aggregation (`>= 80k` DOFs / `PCG_AMG`) para resolver todos los `LoadCase` en paralelo lógico.

### 3.3. Post-Proceso y Verificación
- Desplazamientos nodales $\mathbf{u}$ y magnitud $\|\mathbf{u}\|$.
- Tensión equivalente de **Von Mises**:

$$
\sigma_{vM} = \sqrt{\frac{1}{2}\left[(\sigma_x-\sigma_y)^2 + (\sigma_y-\sigma_z)^2 + (\sigma_z-\sigma_x)^2 + 6(\tau_{xy}^2 + \tau_{yz}^2 + \tau_{xz}^2)\right]}
$$

- Factor de seguridad $SF = \sigma_{\text{yield}} / \max(\sigma_{vM}, \varepsilon)$.
- Chequeo de equilibrio estático global: $\left\|\sum \mathbf{R} + \sum \mathbf{f}_{\text{ext}}\right\| / \|\mathbf{f}_{\text{ext}}\| < 10^{-6}$.

---

## 4. Optimización Topológica 3D: SIMP con OC y MMA (Fase 3)

### 4.1. Interpolación SIMP Modificada
$$
E_e(\tilde{\rho}_e) = E_{\min} + \tilde{\rho}_e^p (E_0 - E_{\min}), \qquad p = 3.0, \qquad E_{\min} = 10^{-9} E_0
$$

### 4.2. Objetivo Multi-Loadcase y Filtrado
- **Compliance ponderado:** $c(\tilde{\boldsymbol{\rho}}) = \sum_{l=1}^{L} w_l \, (\mathbf{u}^{(l)})^T \mathbf{K}(\tilde{\boldsymbol{\rho}}) \mathbf{u}^{(l)}$.
- **Filtro cónico de densidad:** $\tilde{\boldsymbol{\rho}} = (\mathbf{H}\boldsymbol{\rho}) / \mathbf{h}_{\text{sum}}$ con radio $r_{\min} \ge 1.5\, h_e$ para evitar *checkerboarding* y dependencia de malla, propagando la regla de la cadena exacta en todas las sensibilidades.
- **Proyección Heaviside + Continuación:** rampa progresiva de $p$ (y $\beta$) para obtener fronteras nítidas $0/1$.
- **Zonas no-diseño (`DesignZone`):** elementos pasivos sólidos ($\rho_e = 1$ en taladros y apoyos) y pasivos vacíos ($\rho_e = 0$ en canales de paso).

### 4.3. Optimizadores: OC vs. MMA y Restricción de Tensión P-Norma
- **Optimality Criteria (`OC`):** bisección rápida para el problema clásico de minimizar compliance con una única restricción de volumen.
- **Method of Moving Asymptotes (`MMA` — adaptado de `pyMOTO`, licencia MIT):** habilita optimización multi-restricción incluyendo **restricción de tensión máxima de Von Mises** mediante agregación **P-norma** con escalado adaptativo (`StressConstraintConfig`):

$$
\sigma_{PN} = \left( \sum_{e} \left(\frac{\hat{\sigma}_{vM,e}}{\sigma_{\max}}\right)^P \right)^{1/P}
$$

*(Nota de dominio: `TopOptStudyConfig` exige `OptimizerKind.MMA` siempre que `stress_constraint.enabled = True`.)*

### 4.4. Reconstrucción Watertight `.STL` y Métricas de Ahorro de Peso
1. Padding con halo de ceros de 1 vóxel para cerrar fronteras exteriores.
2. Extracción de isosuperficie por Marching Cubes en umbral $\tau$ ajustado al volumen objetivo.
3. Suavizado **Taubin** preservador de volumen (evita adelgazamiento de barras).
4. Auditoría de variedad/*watertightness* antes de exportar `.STL` binario.
5. Cálculo consistente de ahorro de masa (`WeightSavingsMetrics` en `src/topo_logic/domain/results.py`): masa original, masa optimizada y masa ahorrada en **`kg`** y **`g`**, más el porcentaje de reducción (`mass_reduction_percent`), convirtiendo automáticamente desde densidad `tonne/mm³` (`mm_N_MPa`) o `kg/m³` (`m_N_Pa`).
