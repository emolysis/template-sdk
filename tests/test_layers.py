"""Internal layering: a module imports only modules listed before it (docs/architecture.md)."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import REPO

ORDER = [
    "spec",
    "problems",
    "yamlio",
    "slots",
    "template",
    "validate",
    "render",
    "runner",
    "scaffold",
    "cli",
    "__main__",
]
PACKAGE = REPO / "src" / "emolysis_template_sdk"


def _internal_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module == "emolysis_template_sdk":
            found.update(alias.name for alias in node.names)
    return found


def test_every_module_is_placed() -> None:
    modules = {p.stem for p in PACKAGE.glob("*.py")} - {"__init__"}
    assert modules == set(ORDER)


def test_imports_point_down() -> None:
    for index, module in enumerate(ORDER):
        allowed = set(ORDER[:index])
        imports = _internal_imports(PACKAGE / f"{module}.py")
        assert imports <= allowed, f"{module} imports {sorted(imports - allowed)}"
