"""Rendering and slot value checks."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

from conftest import VALID
from emolysis_template_sdk import DIALECTS, RenderError, Slot, load_template, render
from emolysis_template_sdk.slots import (
    check_expression,
    check_value,
    parse_duration,
    render_value,
    scan_placeholders,
    substitute,
)

ALL_TYPES = """
slots:
  - {name: ident, type: identifier, required: true}
  - {name: tbl, type: table, required: true}
  - {name: col, type: column, required: true}
  - {name: cols, type: columns, required: true}
  - {name: expr, type: expression, required: true}
  - {name: exprs, type: expressions, required: true}
  - {name: text, type: string, required: true}
  - {name: num, type: integer, required: true}
  - {name: flag, type: boolean, required: true}
  - {name: window, type: duration, required: true}
  - {name: mode, type: enum, enum: [merge, overwrite], default: merge}
"""

ALL_SQL = (
    "SELECT {{ ident }}, {{ col }}, {{ cols }}, {{ expr }} AS e, {{ exprs }}, {{ text }} AS t,\n"
    "  {{ num }} AS n, {{ flag }} AS f, {{ window }} AS w, '{{ mode }}' AS m\n"
    "FROM {{ tbl }};\n"
)

ALL_PY = (
    "IDENT = {{ ident }}\nTBL = {{ tbl }}\nCOL = {{ col }}\nCOLS = {{ cols }}\n"
    "EXPR = {{ expr }}\nEXPRS = {{ exprs }}\nTEXT = {{ text }}\nNUM = {{ num }}\n"
    "FLAG = {{ flag }}\n"
    "WINDOW = {{ window }}\nMODE = {{ mode }}\n\n\ndef run(con):\n    pass\n"
)

VALUES: dict[str, object] = {
    "ident": "order_id",
    "tbl": "sales.orders",
    "col": "amount",
    "cols": ["region", "channel"],
    "expr": "status <> 'cancelled'",
    "exprs": ["count(*) AS n", "sum(amount) total"],
    "text": "it's",
    "num": 7,
    "flag": True,
    "window": "2 days",
}


def all_types_template(tmp: Path, platform: str, entry: str) -> Path:
    root = tmp / f"all-{platform}-{entry}"
    root.mkdir()
    (root / "template.yaml").write_text(
        "format: emolysis.template/v0\n"
        f"id: snapshot.{platform}\nshape: snapshot\nplatform: {platform}\n"
        "version: 0.1.0\ntitle: All slot types\ndescription: Test.\n"
        f"entry: {entry}\n" + ALL_TYPES
    )
    (root / entry).write_text(ALL_SQL if entry.endswith(".sql") else ALL_PY)
    (root / "cost.md").write_text("Test.\n")
    (root / "profile_constraints.json").write_text(
        f'{{"platform": "{platform}", "profile_version": ">=1", "requires": [], "forbids": []}}'
    )
    return root


def test_render_every_type_duckdb(tmp_path: Path) -> None:
    template = load_template(all_types_template(tmp_path, "duckdb", "template.sql"))
    assert render(template, VALUES) == (
        "SELECT order_id, amount, region, channel, status <> 'cancelled' AS e,"
        " COUNT(*) AS n, SUM(amount) AS total, 'it''s' AS t,\n"
        "  7 AS n, TRUE AS f, INTERVAL '2' DAY AS w, 'merge' AS m\n"
        "FROM sales.orders;\n"
    )


def test_render_uses_dialect_literals(tmp_path: Path) -> None:
    template = load_template(all_types_template(tmp_path, "snowflake", "template.sql"))
    rendered = render(template, {**VALUES, "mode": "overwrite"})
    assert "'it\\'s' AS t" in rendered
    assert "INTERVAL '2 DAY' AS w" in rendered
    assert "'overwrite' AS m" in rendered
    databricks = load_template(all_types_template(tmp_path, "databricks", "template.sql"))
    assert "'it\\'s' AS t" in render(databricks, VALUES)


TRICKY = "it's a \\ back\nslash; -- not a comment {{ x }}"


@pytest.mark.parametrize(
    ("dialect", "string", "backslash", "duration"),
    [
        ("duckdb", "'it''s'", "'a\\b'", "INTERVAL '2' DAY"),
        ("databricks", "'it\\'s'", "'a\\\\b'", "INTERVAL '2' DAY"),
        ("spark", "'it\\'s'", "'a\\\\b'", "INTERVAL '2' DAY"),
        ("snowflake", "'it\\'s'", "'a\\\\b'", "INTERVAL '2 DAY'"),
    ],
)
def test_literals_render_per_dialect(
    dialect: str, string: str, backslash: str, duration: str
) -> None:
    """The examples in docs/format.md section 4."""
    assert render_value(Slot(name="s", type="string"), "it's", "sql", dialect) == string
    assert render_value(Slot(name="s", type="string"), "a\\b", "sql", dialect) == backslash
    assert render_value(Slot(name="b", type="boolean"), True, "sql", dialect) == "TRUE"
    assert render_value(Slot(name="d", type="duration"), "2 days", "sql", dialect) == duration


@pytest.mark.parametrize("dialect", sorted(set(DIALECTS.values())))
def test_string_literals_round_trip_in_their_dialect(dialect: str) -> None:
    text = render_value(Slot(name="s", type="string"), TRICKY, "sql", dialect)
    parsed = sqlglot.parse_one(text, read=dialect)
    assert isinstance(parsed, exp.Literal)
    assert parsed.is_string
    assert parsed.this == TRICKY


@pytest.mark.parametrize("dialect", sorted(set(DIALECTS.values())))
@pytest.mark.parametrize(
    ("value", "unit", "amount"),
    [("15m", "MINUTE", "15"), ("36 Hours", "HOUR", "36"), ("1 week", "WEEK", "1")],
)
def test_duration_literals_parse_back_in_their_dialect(
    dialect: str, value: str, unit: str, amount: str
) -> None:
    text = render_value(Slot(name="d", type="duration"), value, "sql", dialect)
    parsed = sqlglot.parse_one(text, read=dialect)
    assert isinstance(parsed, exp.Interval)
    assert parsed.text("unit").upper() == unit
    assert parsed.this.name == amount


def test_render_python_literals(tmp_path: Path) -> None:
    template = load_template(all_types_template(tmp_path, "duckdb", "template.py"))
    rendered = render(template, VALUES)
    namespace: dict[str, object] = {}
    exec(compile(rendered, "template.py", "exec"), namespace)
    assert namespace["IDENT"] == "order_id"
    assert namespace["TBL"] == "sales.orders"
    assert namespace["COLS"] == ["region", "channel"]
    assert namespace["EXPR"] == "status <> 'cancelled'"
    assert namespace["EXPRS"] == ["count(*) AS n", "sum(amount) total"]
    assert namespace["TEXT"] == "it's"
    assert namespace["NUM"] == 7
    assert namespace["FLAG"] is True
    assert namespace["WINDOW"] == 2 * 86400
    assert namespace["MODE"] == "merge"


def test_render_defaults_and_overrides(tmp_path: Path) -> None:
    template = load_template(all_types_template(tmp_path, "duckdb", "template.sql"))
    rendered = render(template, VALUES)
    assert "'merge' AS m" in rendered
    assert "{{" not in rendered
    rendered = render(template, {**VALUES, "mode": "overwrite"})
    assert "'overwrite' AS m" in rendered


def test_render_errors_are_collected() -> None:
    template = load_template(VALID / "minimal")
    with pytest.raises(RenderError) as raised:
        render(template, {"source_table": "bad name", "extra": 1})
    found = {p.code for p in raised.value.problems}
    assert found == {"slot-unknown", "slot-value-invalid", "slot-missing"}


def test_render_without_values_needs_required_slots() -> None:
    with pytest.raises(RenderError):
        render(load_template(VALID / "minimal"))


GOOD: list[tuple[str, object]] = [
    ("identifier", "a_1"),
    ("identifier", "_x"),
    ("table", "t"),
    ("table", "s.t"),
    ("table", "c.s.t"),
    ("column", "Amount"),
    ("columns", ["a"]),
    ("columns", ["a", "b"]),
    ("expression", "a + 1"),
    ("expression", "x IN (SELECT 1)"),
    ("expression", "CASE WHEN a THEN 1 ELSE 0 END"),
    ("expression", "1 = 1 -- trailing comment"),
    ("string", ""),
    ("string", "anything; even DROP TABLE"),
    ("integer", 0),
    ("integer", -5),
    ("boolean", False),
    ("duration", "15m"),
    ("duration", "1 week"),
    ("duration", "36 Hours"),
    ("enum", "merge"),
]

BAD: list[tuple[str, object]] = [
    ("identifier", "a-b"),
    ("identifier", "1a"),
    ("identifier", 3),
    ("table", "a.b.c.d"),
    ("table", "a..b"),
    ("table", "t; DROP TABLE x"),
    ("column", ""),
    ("columns", []),
    ("columns", "a, b"),
    ("columns", ["a", "A"]),
    ("columns", ["a", 1]),
    ("expression", ""),
    ("expression", "1; DROP TABLE x"),
    ("expression", "SELECT 1"),
    ("expression", "x FROM t"),
    ("expression", "a AS b"),
    ("expression", "DROP TABLE x"),
    ("expression", "(("),
    ("expression", 5),
    ("string", 5),
    ("string", None),
    ("integer", True),
    ("integer", 1.5),
    ("integer", "1"),
    ("boolean", "true"),
    ("boolean", 1),
    ("duration", "2"),
    ("duration", "2 fortnights"),
    ("duration", 3600),
    ("enum", "append"),
    ("enum", 1),
]


def _slot(kind: str) -> Slot:
    return Slot(name="s", type=kind, enum=("merge", "overwrite") if kind == "enum" else ())


@pytest.mark.parametrize(("kind", "value"), GOOD)
def test_good_values(kind: str, value: object) -> None:
    assert check_value(_slot(kind), value, "duckdb") is None


@pytest.mark.parametrize(("kind", "value"), BAD)
def test_bad_values(kind: str, value: object) -> None:
    assert check_value(_slot(kind), value, "duckdb") is not None


def test_unknown_slot_type_is_rejected() -> None:
    assert check_value(_slot("timestamp"), "x", "duckdb") == "unknown slot type 'timestamp'"


def test_expression_is_checked_in_the_template_dialect() -> None:
    assert check_expression("`region` = 'north'", "databricks") is None
    assert check_expression("IFF(a, 1, 2)", "snowflake") is None


def test_parse_duration() -> None:
    assert parse_duration("2 days") == (2, "DAY", 172800)
    assert parse_duration("90s") == (90, "SECOND", 90)
    assert parse_duration("2") is None


def test_scan_placeholders() -> None:
    scan = scan_placeholders(
        "a {{ x }} b {{y}}\n{{ x }} {{ x | upper }} {% if %} {# c #} {{{ z }}}"
    )
    assert scan.used == {"x": 1, "y": 1}
    assert [line for line, _ in scan.invalid] == [2, 2, 2, 2]


def test_substitute_is_textual() -> None:
    assert substitute("-- {{ a }}\n'{{ a }}'", {"a": "v"}) == "-- v\n'v'"


def test_render_value_columns_sql() -> None:
    slot = Slot(name="c", type="columns")
    assert render_value(slot, ["a", "b"], "sql", "duckdb") == "a, b"
    assert render_value(slot, ["a", "b"], "python", "duckdb") == "['a', 'b']"
