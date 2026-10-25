"""The package imports each public name on its first use (docs/specs/sdk.md, "Package"):
importing it loads none of its modules, and `write_identifier` and `write_table` load
neither DuckDB nor the runner."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys

import pytest

import emolysis_template_sdk as sdk

HEAVY = ("duckdb", "yaml", "jsonschema", "emolysis_template_sdk.runner")


def _loaded_after(code: str) -> list[str]:
    """The SDK's own modules and the heavy ones loaded in a fresh interpreter by `code`."""
    probe = (
        f"import json, sys\n{code}\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        f"if m.startswith(('emolysis_template_sdk',) + {HEAVY!r}))))\n"
    )
    ran = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True
    )
    loaded: list[str] = json.loads(ran.stdout)
    return loaded


def test_importing_the_package_loads_none_of_its_modules() -> None:
    assert _loaded_after("import emolysis_template_sdk") == ["emolysis_template_sdk"]


def test_writing_a_name_loads_neither_duckdb_nor_the_runner() -> None:
    loaded = _loaded_after("from emolysis_template_sdk import write_identifier, write_table")
    assert loaded == [
        "emolysis_template_sdk",
        "emolysis_template_sdk.reserved",
        "emolysis_template_sdk.reserved_duckdb",
    ]
    assert not set(loaded) & set(HEAVY)


@pytest.mark.parametrize("name", sdk.__all__)
def test_every_public_name_resolves_to_its_module_s_object(name: str) -> None:
    module = importlib.import_module(f"emolysis_template_sdk.{sdk._EXPORTS[name]}")
    assert getattr(sdk, name) is getattr(module, name)


def test_the_exports_are_the_public_names() -> None:
    assert sorted(sdk._EXPORTS) == sorted(sdk.__all__)


def test_render_and_validate_stay_functions_once_their_modules_are_imported() -> None:
    code = (
        "import emolysis_template_sdk as sdk, emolysis_template_sdk.runner\n"
        "import emolysis_template_sdk.render, emolysis_template_sdk.validate\n"
        "print(sdk.render.__name__, callable(sdk.render), sdk.validate.__name__)"
    )
    ran = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert ran.stdout.split() == ["render", "True", "validate"]


def test_an_unknown_name_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no attribute 'nothing_here'"):
        _ = sdk.nothing_here
