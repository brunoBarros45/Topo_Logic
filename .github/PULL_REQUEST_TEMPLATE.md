## Summary

<!-- Describe what this Pull Request implements, fixes, or releases. -->

## Pull Request Type

- [ ] Feature / Fix / Docs into **`develop`** (`feat/*`, `fix/*`, `docs/*`, `refactor/*`, `chore/*`, `ci/*`)
- [ ] **Release PR: `develop` → `main`** (stable milestone promotion)

## Verification Checklist

- [ ] Commits follow **Conventional Commits** (`<type>(<scope>): <imperative summary>`)
- [ ] `ruff check src tests` passes with zero warnings/errors
- [ ] `mypy src/topo_logic` passes (`Success: no issues found`)
- [ ] `pytest -v` passes all AST boundary, unit, integration, and analytical benchmark tests
- [ ] Strict **MIT License Hygiene** respected (no GPL/LGPL/PolyForm code copied)
- [ ] Documentation updated where applicable (`README.md`, `ROADMAP.md`, `CHANGELOG.md`, `docs/`)
