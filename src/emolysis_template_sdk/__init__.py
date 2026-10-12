"""Emolysis template SDK: the template format v0, its validator and a local test runner.

Library API:

- `load_template(path) -> Template` loads a template, raising `TemplateError` if invalid.
- `validate(path) -> list[Problem]` checks a template directory and never raises.
- `render(template, slot_values) -> str` substitutes slot values into the entry file.
- `run_tests(path) -> RunReport` runs every test case on DuckDB.
- `new_template(shape, platform, dir)` writes a valid skeleton.

The format is specified in docs/format.md.
"""

from __future__ import annotations

from .problems import Problem, RenderError, Severity, TemplateError, errors
from .render import render
from .runner import CaseResult, RunReport, run_tests, transpile_to_duckdb
from .scaffold import new_template
from .slots import Slot
from .spec import DIALECTS, FORMAT_V0, PLATFORMS, SHAPES, SLOT_TYPES
from .template import ProfileConstraints, Template
from .validate import constraints_schema, load_template, manifest_schema, validate

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
]
