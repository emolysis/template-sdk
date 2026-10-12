"""Strict YAML reading."""

from __future__ import annotations

import pytest

from emolysis_template_sdk.yamlio import YamlError, load_yaml


def test_core_schema_scalars() -> None:
    data = load_yaml(
        "a: yes\nb: true\nc: 2026-10-12\nd: 12:30\ne: 017\nf: 1.5\ng: 0x1F\nh: ~\ni: False\n"
    )
    assert data == {
        "a": "yes",
        "b": True,
        "c": "2026-10-12",
        "d": "12:30",
        "e": 17,
        "f": 1.5,
        "g": "0x1F",
        "h": None,
        "i": False,
    }


@pytest.mark.parametrize(
    "text",
    ["a: 1\na: 2\n", "a: [\n", "? [1]\n: 2\n", "a: !!python/object:os.system x\n", "a: !!int x\n"],
)
def test_bad_documents_raise_yaml_error(text: str) -> None:
    with pytest.raises(YamlError):
        load_yaml(text)
