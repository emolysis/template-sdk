"""Emolysis template SDK: the template format v0, its validator and a local test runner.

Library API:

- `load_template(path) -> Template` loads a template, raising `TemplateError` if invalid.
- `validate(path) -> list[Problem]` checks a template directory and never raises.
- `render(template, slot_values) -> str` substitutes slot values into the entry file.
- `run_tests(path) -> RunReport` runs every test case on DuckDB.
- `new_template(shape, platform, dir)` writes a valid skeleton.
- `write_identifier(name, dialect)` and `write_table(name, dialect)` write a name as a slot
  value renders in that dialect.

The format is specified in docs/format.md. Each name is imported on its first use, so
importing the package loads none of its modules; `write_identifier` loads neither DuckDB
nor the runner.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .problems import Problem, RenderError, Severity, TemplateError, errors
    from .render import render
    from .reserved import write_identifier, write_table
    from .runner import CaseResult, RunReport, run_tests, transpile_to_duckdb
    from .scaffold import new_template
    from .slots import Slot
    from .spec import DIALECTS, FORMAT_V0, PLATFORMS, SHAPES, SLOT_TYPES
    from .template import ProfileConstraints, Template
    from .validate import constraints_schema, load_template, manifest_schema, validate

_EXPORTS: dict[str, str] = {
    "DIALECTS": "spec",
    "FORMAT_V0": "spec",
    "PLATFORMS": "spec",
    "SHAPES": "spec",
    "SLOT_TYPES": "spec",
    "CaseResult": "runner",
    "Problem": "problems",
    "ProfileConstraints": "template",
    "RenderError": "problems",
    "RunReport": "runner",
    "Severity": "problems",
    "Slot": "slots",
    "Template": "template",
    "TemplateError": "problems",
    "constraints_schema": "validate",
    "errors": "problems",
    "load_template": "validate",
    "manifest_schema": "validate",
    "new_template": "scaffold",
    "render": "render",
    "run_tests": "runner",
    "transpile_to_duckdb": "runner",
    "validate": "validate",
    "write_identifier": "reserved",
    "write_table": "reserved",
}
"""The module of this package each public name comes from."""

__all__ = [
    "DIALECTS",
    "FORMAT_V0",
    "PLATFORMS",
    "SHAPES",
    "SLOT_TYPES",
    "CaseResult",
    "Problem",
    "ProfileConstraints",
    "RenderError",
    "RunReport",
    "Severity",
    "Slot",
    "Template",
    "TemplateError",
    "constraints_schema",
    "errors",
    "load_template",
    "manifest_schema",
    "new_template",
    "render",
    "run_tests",
    "transpile_to_duckdb",
    "validate",
    "write_identifier",
    "write_table",
]


def __getattr__(name: str) -> object:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


class _Package(types.ModuleType):
    """This package. `render` and `validate` name both a public function and the module it
    comes from; importing such a module sets the package's attribute to the module, which
    would hide the function, so a public name is never set to a module."""

    def __setattr__(self, name: str, value: object) -> None:
        if name in _EXPORTS and isinstance(value, types.ModuleType):
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Package
