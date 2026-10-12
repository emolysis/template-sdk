"""Strict YAML reading for template.yaml and slots.yaml.

PyYAML follows YAML 1.1, where `yes`, `no`, `on` and `off` are booleans, `2026-10-12` is
a date, `12:30` is the integer 750 and `017` is octal. Format v0 reads YAML with
core-schema scalars instead: only `true` and `false` are booleans, integers are decimal,
and dates and times stay strings. Duplicate mapping keys are an error.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node

_BOOL_RE = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_RE = re.compile(r"^[-+]?[0-9]+$")
_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)
_REPLACED_TAGS = (
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:timestamp",
)


class StrictLoader(yaml.SafeLoader):
    """SafeLoader with core-schema booleans, no timestamps and no duplicate keys."""


# Drop the YAML 1.1 bool, int, float and timestamp resolvers, then add core-schema ones.
StrictLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag not in _REPLACED_TAGS]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:bool", _BOOL_RE, list("tTfF"))
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:int", _INT_RE, list("-+0123456789"))
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:float", _FLOAT_RE, list("-+0123456789."))


def _construct_int(loader: StrictLoader, node: Node) -> int:
    value = loader.construct_scalar(node)  # type: ignore[arg-type]
    return int(str(value), 10)


StrictLoader.add_constructor("tag:yaml.org,2002:int", _construct_int)


def _construct_mapping(loader: StrictLoader, node: Node, deep: bool = False) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "expected a mapping", node.start_mark)
    loader.flatten_mapping(node)
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in seen
        except TypeError:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from None
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        seen.add(key)
    return dict(loader.construct_pairs(node, deep=deep))


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


class YamlError(Exception):
    """A YAML document could not be read. `line` is 1-based when known."""

    def __init__(self, message: str, line: int | None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


def load_yaml(text: str) -> object:
    """Parse one YAML document with the strict loader. Raises `YamlError`."""
    try:
        # StrictLoader derives from SafeLoader, so this never builds arbitrary objects.
        return yaml.load(text, Loader=StrictLoader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 if mark is not None else None
        problem = exc.problem or "invalid YAML"
        if exc.context:
            problem = f"{exc.context}: {problem}"
        raise YamlError(problem, line) from None
    except yaml.YAMLError as exc:
        raise YamlError(str(exc) or "invalid YAML", None) from None
    except (ValueError, OverflowError, RecursionError) as exc:
        # Scalar construction can still fail, for example on huge integers.
        raise YamlError(f"invalid YAML value: {exc}", None) from None
