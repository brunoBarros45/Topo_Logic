# ADR-0005: Sistema Consistente de Unidades, Guardia de Escala e Higiene MIT

- **Estado:** Aceptado
- **Fecha:** 2026-11-18

## Contexto
1. Los archivos `.STL` (formato elegido para la Fase 1) carecen de metadatos de unidades; confundir `mm` con `m` introduce errores de rigidez de $10^9\times$.
2. `Topo_Logic` es estrictamente **MIT**. Algunas librerías populares del ecosistema CAE (`libgmsh`, `mmapy`, `TopOpt_in_PETSc`) tienen licencias GPL o LGPL.

## Decisión
1. Exigir un `UnitSystem` explícito (`mm_N_MPa` o `m_N_Pa`) y `AxisConvention` (`Z_up` o `Y_up`) en cada ingesta, ejecutando automáticamente `evaluate_scale_guard()` para advertir escalas sospechosas (`m` con $D > 20$ o `mm` con $D < 1$).
2. Mantener **100% de dependencias MIT/BSD/Apache-2.0** en el paquete Python core (`numpy`, `scipy`, `trimesh`, `scikit-fem`, `pyamg`, `scikit-image`, `fastapi`, `pydantic`).
3. El mallado volumétrico nativo rápido usará un mallador hexaédrico `H8` puro **MIT**; cuando se incorpore `Gmsh` para `C3D10` no estructurado (Fase 2), operará únicamente como **adaptador CLI externo por subproceso** detrás de `VolumetricMesherPort`, sin enlazar `libgmsh` GPL en el paquete principal.

## Alternativas Consideradas
- **Incluir `gmsh` Python wheel como dependencia obligatoria en `pyproject.toml`:** Descartado para evitar dudas de licenciamiento GPL sobre el paquete MIT distribuido.

## Consecuencias
- **Positivas:** Seguridad jurídica total para usuarios académicos y comerciales bajo MIT, y prevención automática de errores catastróficos de unidades desde el primer endpoint.
- **Negativas / Mitigación:** El usuario que requiera tetraedros `C3D10` en Fase 2 deberá tener el binario CLI de Gmsh disponible si opta por `C3D10` (mientras que `H8` funcionará siempre sin dependencias externas).
