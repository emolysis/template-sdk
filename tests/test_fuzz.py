"""Fuzz: validate() and render() stay total, and rendered SQL keeps its shape.

validate() never raises and never hits the internal-error path; an `expressions` value
renders as exactly one select-list item per list entry; string literals round-trip in
every dialect.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlglot import exp

from conftest import VALID
from emolysis_template_sdk import (
    DIALECTS,
    PLATFORMS,
    SHAPES,
    SLOT_TYPES,
    RenderError,
    Slot,
    load_template,
    render,
    validate,
)
from emolysis_template_sdk.slots import (
    check_select_item,
    check_value,
    normalize_select_item,
    render_value,
)

FUZZ = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

scalars = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**70), max_value=2**70)
    | st.floats(allow_nan=False)
    | st.text(max_size=30)
    | st.sampled_from(["", "x", "1.0", "true", "{{ x }}", "a.b.c.d", "2 days", "merge"])
)
values = st.recursive(
    scalars,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=12,
)

slot_entries = st.fixed_dictionaries(
    {},
    optional={
        "name": st.sampled_from(["source_table", "target_table", "x", "Bad Name", ""]) | values,
        "type": st.sampled_from([*SLOT_TYPES, "timestamp"]) | values,
        "required": st.booleans() | values,
        "default": values,
        "description": st.text(max_size=20) | values,
        "enum": st.lists(st.sampled_from(["merge", "overwrite", "a b", ""]), max_size=3) | values,
        "x-extra": values,
        "surprise": values,
    },
)

manifests = st.fixed_dictionaries(
    {},
    optional={
        "format": st.sampled_from(["emolysis.template/v0", "emolysis.template/v1", "v0"]) | values,
        "id": st.sampled_from(["snapshot.duckdb", "scd2.databricks", "x"]) | values,
        "shape": st.sampled_from([*SHAPES, "star"]) | values,
        "platform": st.sampled_from([*PLATFORMS, "bigquery"]) | values,
        "version": st.sampled_from(["0.1.0", "1", "1.0.0-rc.1"]) | values,
        "title": st.text(max_size=20) | values,
        "description": st.text(max_size=20) | values,
        "entry": st.sampled_from(["template.sql", "template.py", "other.sql"]) | values,
        "slots": st.lists(slot_entries, max_size=4) | values,
        "x-note": values,
        "unexpected": values,
    },
)


def _copy_minimal(tmp: str) -> Path:
    root = Path(tmp) / "t"
    shutil.copytree(VALID / "minimal", root)
    return root


def _assert_total(root: Path) -> None:
    problems = validate(root)
    assert isinstance(problems, list)
    assert not [p for p in problems if p.code == "internal"], [str(p) for p in problems]


@FUZZ
@given(manifest=manifests)
def test_validate_never_raises_on_random_manifests(manifest: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = _copy_minimal(tmp)
        (root / "template.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
        _assert_total(root)


@FUZZ
@given(slots=st.lists(slot_entries, max_size=5))
def test_validate_never_raises_on_random_slots(slots: list[dict[str, Any]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = _copy_minimal(tmp)
        manifest = yaml.safe_load((root / "template.yaml").read_text())
        manifest["slots"] = slots
        (root / "template.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
        _assert_total(root)


@FUZZ
@given(
    manifest=st.binary(max_size=200) | st.text(max_size=200).map(str.encode),
    entry=st.text(max_size=200),
    slot_values=st.binary(max_size=100) | values.map(lambda v: yaml.safe_dump(v).encode()),
    constraints=st.binary(max_size=100) | st.text(max_size=100).map(str.encode),
)
def test_validate_never_raises_on_random_files(
    manifest: bytes, entry: str, slot_values: bytes, constraints: bytes
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = _copy_minimal(tmp)
        (root / "template.sql").write_text(entry, encoding="utf-8")
        (root / "tests" / "basic" / "slots.yaml").write_bytes(slot_values)
        (root / "profile_constraints.json").write_bytes(constraints)
        _assert_total(root)
        (root / "template.yaml").write_bytes(manifest)
        _assert_total(root)


@FUZZ
@given(kind=st.sampled_from([*SLOT_TYPES, "unknown"]), value=values)
def test_check_value_never_raises(kind: str, value: object) -> None:
    slot = Slot(name="s", type=kind, enum=("merge",) if kind == "enum" else ())
    for dialect in ("duckdb", "databricks", "snowflake", "spark"):
        result = check_value(slot, value, dialect)
        assert result is None or isinstance(result, str)


@FUZZ
@given(slot_values=st.dictionaries(st.sampled_from(["source_table", "target_table", "x"]), values))
def test_render_raises_only_render_error(slot_values: dict[str, object]) -> None:
    template = load_template(VALID / "minimal")
    problems: list[object] = []
    try:
        rendered = render(template, slot_values)
    except RenderError as exc:
        problems.extend(exc.problems)
        rendered = ""
    assert bool(problems) != bool(rendered)


ENGINE_DIALECTS = sorted(set(DIALECTS.values()))

sql_atoms = st.sampled_from(
    [
        "amount",
        "t.amount",
        "`amount`",
        '"amount"',
        "1",
        "2.5",
        "'x'",
        "'it''s'",
        "'a\\'b'",
        "NULL",
        "TRUE",
        "*",
        "(SELECT 1)",
        "INTERVAL '2' DAY",
    ]
)
sql_noise = st.text(alphabet="ab_ ()'\"`,;*+-/\\\n#:{}", max_size=12)


def _compose(inner: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    functions = st.sampled_from(["sum", "count", "max", "coalesce", "upper", "IFF", "nvl"])
    operators = st.sampled_from(["+", "*", "=", "<>", "AND", "OR", "||", "IS"])
    return st.one_of(
        st.tuples(functions, st.lists(inner, min_size=1, max_size=3)).map(
            lambda t: f"{t[0]}({', '.join(t[1])})"
        ),
        st.tuples(inner, operators, inner).map(" ".join),
        st.tuples(inner, inner).map(lambda t: f"CASE WHEN {t[0]} THEN {t[1]} END"),
        st.tuples(inner, inner).map(lambda t: f"{t[0]} FILTER (WHERE {t[1]})"),
        st.tuples(inner, inner).map(lambda t: f"{t[0]} -- {t[1]}\n"),
        st.tuples(inner, inner).map(lambda t: f"{t[0]} /* {t[1]} */"),
        st.tuples(inner, inner).map(lambda t: f"{t[0]}, {t[1]}"),
        inner.map(lambda x: f"({x})"),
    )


sql_expressions = st.recursive(sql_atoms | sql_noise, _compose, max_leaves=6)
aliases = st.none() | st.sampled_from(["total", "n_1", '"Mixed Name"', "`x y`", "select", ""])
select_items = st.tuples(sql_expressions, aliases).map(
    lambda t: t[0] if t[1] is None else f"{t[0]} AS {t[1]}"
)
expression_lists = st.lists(select_items, max_size=4)


@FUZZ
@given(items=expression_lists | values)
def test_expressions_check_never_raises(items: object) -> None:
    slot = Slot(name="m", type="expressions", required=True)
    for dialect in ENGINE_DIALECTS:
        result = check_value(slot, items, dialect)
        assert result is None or isinstance(result, str)


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(items=expression_lists)
def test_expressions_render_one_select_item_each(items: list[str]) -> None:
    slot = Slot(name="m", type="expressions", required=True)
    for dialect in ENGINE_DIALECTS:
        if check_value(slot, items, dialect) is not None:
            continue
        rendered = render_value(slot, items, "sql", dialect)
        statements = sqlglot.parse(f"SELECT {rendered} FROM t", read=dialect)
        assert len(statements) == 1, (dialect, items, rendered)
        select = statements[0]
        assert isinstance(select, exp.Select), (dialect, items, rendered)
        assert len(select.expressions) == len(items), (dialect, items, rendered)
        others = {k for k, v in select.args.items() if v not in (None, [], False)}
        assert others in ({"expressions", "from"}, {"expressions", "from_"}), others
        for item in items:
            once = normalize_select_item(item, dialect)
            assert check_select_item(once, dialect) is None, (dialect, item, once)
            assert normalize_select_item(once, dialect) == once, (dialect, item, once)


@FUZZ
@given(value=st.text(max_size=40))
def test_string_literals_round_trip_in_every_dialect(value: str) -> None:
    slot = Slot(name="s", type="string", required=True)
    for dialect in ENGINE_DIALECTS:
        text = render_value(slot, value, "sql", dialect)
        parsed = sqlglot.parse_one(text, read=dialect)
        assert isinstance(parsed, exp.Literal), (dialect, value, text)
        assert parsed.is_string
        assert parsed.this == value, (dialect, value, text)
        if "\x00" in value:
            continue  # DuckDB strings cannot hold NUL
        [statement] = sqlglot.transpile(f"SELECT {text}", read=dialect, write="duckdb")
        row = duckdb.sql(statement).fetchone()
        assert row is not None
        assert row[0] == value, (dialect, value, text, statement)
