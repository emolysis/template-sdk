"""Shipped JSON Schemas agree with the vocabulary in spec.py and with the docs."""

from __future__ import annotations

import jsonschema

from conftest import REPO
from emolysis_template_sdk import (
    DIALECTS,
    FORMAT_V0,
    PLATFORMS,
    SHAPES,
    SLOT_TYPES,
    constraints_schema,
    manifest_schema,
)


def test_schemas_are_valid_json_schemas() -> None:
    for schema in (manifest_schema(), constraints_schema()):
        jsonschema.validators.validator_for(schema).check_schema(schema)


def test_manifest_schema_matches_vocabulary() -> None:
    schema = manifest_schema()
    props = schema["properties"]
    assert props["format"]["const"] == FORMAT_V0
    assert props["shape"]["enum"] == list(SHAPES)
    assert props["platform"]["enum"] == list(PLATFORMS)
    assert schema["$defs"]["slot"]["properties"]["type"]["enum"] == list(SLOT_TYPES)


def test_constraints_schema_matches_vocabulary() -> None:
    assert constraints_schema()["properties"]["platform"]["enum"] == list(PLATFORMS)


def test_schema_accessors_return_copies() -> None:
    schema = manifest_schema()
    schema["title"] = "changed"
    assert manifest_schema()["title"] != "changed"


def test_every_platform_has_a_dialect() -> None:
    assert set(DIALECTS) == set(PLATFORMS)
    assert DIALECTS["fabric"] == "spark"


def test_docs_list_every_shape_platform_and_slot_type() -> None:
    text = (REPO / "docs" / "format.md").read_text(encoding="utf-8")
    for name in (*SHAPES, *PLATFORMS, *SLOT_TYPES):
        assert f"`{name}`" in text, name
