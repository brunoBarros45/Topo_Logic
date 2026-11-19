"""AST-based architectural fitness tests enforcing Clean Architecture layer boundaries."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "topo_logic"
STDLIB_ROOTS = frozenset(sys.stdlib_module_names) | {"__future__"}


def _module_name_for_file(py_file: Path) -> str:
    rel = py_file.relative_to(SRC_ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _extract_imported_modules(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    current_module = _module_name_for_file(py_file)
    package_parts = current_module.split(".")
    if py_file.name != "__init__.py":
        package_parts = package_parts[:-1]

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imports.append(node.module)
            else:
                base_parts = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(base_parts)
                target = f"{base}.{node.module}" if node.module else base
                imports.append(target)
    return imports


def _is_stdlib(module_name: str) -> bool:
    return module_name.split(".", maxsplit=1)[0] in STDLIB_ROOTS


@pytest.mark.unit
def test_domain_layer_has_zero_external_or_outer_layer_imports() -> None:
    domain_files = sorted((SRC_ROOT / "domain").rglob("*.py"))
    assert domain_files, "Expected Python modules under src/topo_logic/domain"

    violations: list[str] = []
    for py_file in domain_files:
        for mod in _extract_imported_modules(py_file):
            if (
                _is_stdlib(mod)
                or mod == "topo_logic.domain"
                or mod.startswith("topo_logic.domain.")
            ):
                continue
            violations.append(f"{py_file.name}: forbidden import '{mod}'")

    assert not violations, "Domain layer boundary violations:\n" + "\n".join(violations)


@pytest.mark.unit
def test_application_layer_depends_only_on_stdlib_and_domain() -> None:
    app_files = sorted((SRC_ROOT / "application").rglob("*.py"))
    assert app_files, "Expected Python modules under src/topo_logic/application"

    violations: list[str] = []
    for py_file in app_files:
        for mod in _extract_imported_modules(py_file):
            if (
                _is_stdlib(mod)
                or mod == "topo_logic.domain"
                or mod.startswith("topo_logic.domain.")
                or mod == "topo_logic.application"
                or mod.startswith("topo_logic.application.")
            ):
                continue
            violations.append(f"{py_file.name}: forbidden import '{mod}'")

    assert not violations, "Application layer boundary violations:\n" + "\n".join(violations)


@pytest.mark.unit
def test_infrastructure_layer_never_imports_interfaces_or_web_frameworks() -> None:
    infra_files = sorted((SRC_ROOT / "infrastructure").rglob("*.py"))
    assert infra_files, "Expected Python modules under src/topo_logic/infrastructure"

    forbidden_prefixes = ("topo_logic.interfaces", "fastapi", "uvicorn", "starlette")
    violations: list[str] = []
    for py_file in infra_files:
        for mod in _extract_imported_modules(py_file):
            if any(mod == prefix or mod.startswith(f"{prefix}.") for prefix in forbidden_prefixes):
                violations.append(f"{py_file.name}: forbidden import '{mod}'")

    assert not violations, "Infrastructure layer boundary violations:\n" + "\n".join(violations)
