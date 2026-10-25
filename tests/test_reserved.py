"""Identifier slot values that their dialect reserves (docs/format.md section 4)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import sqlglot
from sqlglot import exp

from conftest import EXAMPLE, EXAMPLES, FIXTURES, VALID, subdirs
from emolysis_template_sdk import Slot, load_template, render, transpile_to_duckdb
from emolysis_template_sdk.reserved import (
    RESERVED,
    SNOWFLAKE_RESERVED,
    write_identifier,
    write_table,
)
from emolysis_template_sdk.reserved_duckdb import DUCKDB_RESERVED
from emolysis_template_sdk.slots import render_value
from emolysis_template_sdk.yamlio import load_yaml

RENDERS = FIXTURES / "renders"

IDENTIFIER = Slot(name="i", type="identifier")
COLUMN = Slot(name="c", type="column")
COLUMNS = Slot(name="cs", type="columns")
TABLE = Slot(name="t", type="table")


@pytest.mark.parametrize(
    ("dialect", "name", "written"),
    [
        ("snowflake", "order", '"ORDER"'),
        ("snowflake", "group", '"GROUP"'),
        ("snowflake", "start", '"START"'),
        ("snowflake", "table", '"TABLE"'),
        ("snowflake", "Order", '"ORDER"'),
        ("snowflake", "GROUP", '"GROUP"'),
        ("duckdb", "order", '"order"'),
        ("duckdb", "group", '"group"'),
        ("duckdb", "table", '"table"'),
        ("duckdb", "end", '"end"'),
        ("duckdb", "Order", '"Order"'),
        ("duckdb", "start", "start"),
        ("databricks", "order", "order"),
        ("databricks", "group", "group"),
        ("databricks", "table", "table"),
        ("spark", "order", "order"),
        ("spark", "group", "group"),
        ("spark", "table", "table"),
    ],
)
def test_a_reserved_name_is_quoted_in_the_case_its_dialect_gives_it(
    dialect: str, name: str, written: str
) -> None:
    assert render_value(IDENTIFIER, name, "sql", dialect) == written
    assert render_value(COLUMN, name, "sql", dialect) == written
    assert render_value(TABLE, name, "sql", dialect) == written


@pytest.mark.parametrize("dialect", ["duckdb", "snowflake", "databricks", "spark"])
@pytest.mark.parametrize(
    "name", ["region", "order_id", "ordered", "date", "user", "value", "timestamp", "_x"]
)
def test_a_name_no_dialect_reserves_is_written_verbatim(dialect: str, name: str) -> None:
    assert render_value(IDENTIFIER, name, "sql", dialect) == name
    assert render_value(COLUMNS, [name, "amount"], "sql", dialect) == f"{name}, amount"
    assert render_value(TABLE, f"sales.{name}", "sql", dialect) == f"sales.{name}"


@pytest.mark.parametrize(
    ("dialect", "columns", "written"),
    [
        ("snowflake", ["order", "region", "group"], '"ORDER", region, "GROUP"'),
        ("duckdb", ["order", "region", "group"], '"order", region, "group"'),
        ("databricks", ["order", "region", "group"], "order, region, group"),
        ("spark", ["order", "region", "group"], "order, region, group"),
    ],
)
def test_each_item_of_columns_is_written_on_its_own(
    dialect: str, columns: list[str], written: str
) -> None:
    assert render_value(COLUMNS, columns, "sql", dialect) == written


@pytest.mark.parametrize(
    ("dialect", "table", "written"),
    [
        ("snowflake", "analytics.group.order", 'analytics."GROUP"."ORDER"'),
        ("snowflake", "table.sales.orders", '"TABLE".sales.orders'),
        ("snowflake", "sales.window", 'sales."WINDOW"'),
        ("duckdb", "main.order", 'main."order"'),
        ("duckdb", "group.sales.orders", '"group".sales.orders'),
        ("databricks", "analytics.group.order", "analytics.group.order"),
        ("spark", "analytics.group.order", "analytics.group.order"),
    ],
)
def test_each_part_of_a_table_name_is_written_on_its_own(
    dialect: str, table: str, written: str
) -> None:
    assert render_value(TABLE, table, "sql", dialect) == written
    assert write_table(table, dialect) == written


def test_python_entries_and_other_slot_types_are_unchanged() -> None:
    assert render_value(IDENTIFIER, "order", "python", "snowflake") == "'order'"
    assert render_value(COLUMNS, ["order", "group"], "python", "duckdb") == "['order', 'group']"
    assert render_value(TABLE, "sales.order", "python", "snowflake") == "'sales.order'"
    assert render_value(Slot(name="e", type="expression"), "order_id + 1", "sql", "snowflake") == (
        "order_id + 1"
    )
    mode = Slot(name="m", type="enum", enum=("order", "group"))
    assert render_value(mode, "order", "sql", "snowflake") == "order"


def test_a_whole_render_quotes_the_reserved_slot_values(tmp_path: Path) -> None:
    template = load_template(VALID / "snowflake-sql")
    rendered = render(
        template, {"source_table": "raw.table", "target_table": "orders", "key_column": "order"}
    )
    assert 'FROM raw."TABLE"\n' in rendered
    assert 'PARTITION BY "ORDER" ORDER BY loaded_at' in rendered
    assert '  "ORDER",\n' in rendered


def test_the_lists_hold_what_their_sources_list() -> None:
    # Snowflake's table lists 92 keywords; DuckDB 1.5 reserves 75 (`duckdb_keywords()`).
    assert len(SNOWFLAKE_RESERVED) == 92
    assert len(DUCKDB_RESERVED) == 75
    assert {"ORDER", "GROUP", "START", "TABLE", "WINDOW", "ROW", "ROWS"} <= SNOWFLAKE_RESERVED
    assert not {"DATE", "USER", "VALUE", "TIMESTAMP", "END"} & SNOWFLAKE_RESERVED
    assert {"order", "group", "end", "table", "window"} <= DUCKDB_RESERVED
    assert not {"date", "user", "value", "timestamp", "start"} & DUCKDB_RESERVED
    assert RESERVED["databricks"] == frozenset()
    assert RESERVED["spark"] == frozenset()
    for words in RESERVED.values():
        assert all(word == word.lower() for word in words)


@pytest.mark.parametrize("word", sorted(DUCKDB_RESERVED))
def test_every_duckdb_word_fails_bare_and_works_written(word: str) -> None:
    con = duckdb.connect()
    try:
        with pytest.raises(duckdb.Error):
            con.execute(f"CREATE TABLE bare ({word} INTEGER)")
        name = write_identifier(word, "duckdb")
        assert name == f'"{word}"'
        con.execute(f"CREATE TABLE {name} ({name} INTEGER, amount INTEGER)")
        con.execute(f"INSERT INTO {name} VALUES (1, 10), (1, 5), (2, 7)")
        rows = con.execute(
            f"SELECT {name}, sum(amount) FROM {name} WHERE {name} > 0 "
            f"GROUP BY {name} ORDER BY {name}"
        ).fetchall()
    finally:
        con.close()
    assert rows == [(1, 15), (2, 7)]


@pytest.mark.parametrize("word", sorted(SNOWFLAKE_RESERVED))
def test_every_snowflake_word_written_parses_as_the_upper_case_column(word: str) -> None:
    name = write_identifier(word.lower(), "snowflake")
    assert name == f'"{word}"'
    select = sqlglot.parse_one(f"SELECT {name} FROM t GROUP BY {name}", read="snowflake")
    column = select.find(exp.Column)
    assert column is not None
    assert column.name == word
    assert column.this.args.get("quoted") is True


def test_the_duckdb_example_runs_on_columns_and_tables_named_with_reserved_words() -> None:
    sql = render(
        load_template(EXAMPLE),
        {
            "source_table": "table",
            "target_table": "window",
            "group_by": ["group", "order"],
            "measures": ["count(*) AS orders", "sum(amount) AS revenue"],
        },
    )
    assert 'CREATE OR REPLACE TABLE "window" AS' in sql
    assert 'GROUP BY "group", "order";' in sql
    con = duckdb.connect()
    try:
        con.execute('CREATE TABLE "table" ("group" VARCHAR, "order" INTEGER, amount INTEGER)')
        con.execute("""INSERT INTO "table" VALUES ('a', 1, 10), ('a', 1, 5), ('b', 2, 7)""")
        con.execute(sql)
        rows = con.execute('SELECT * FROM "window" ORDER BY ALL').fetchall()
    finally:
        con.close()
    assert rows == [("a", 1, 2, 15), ("b", 2, 1, 7)]


def test_a_snowflake_render_runs_on_duckdb_after_transpiling() -> None:
    # `start` is reserved on Snowflake only, `order` on both: transpiled, each names the
    # same column on DuckDB, which matches names case-insensitively.
    sql = render(
        load_template(VALID / "snowflake-sql"),
        {
            "source_table": "raw.table",
            "target_table": "orders",
            "key_column": "order",
            "loaded_at": "start",
        },
    )
    assert 'PARTITION BY "ORDER" ORDER BY "START" DESC' in sql
    statements = transpile_to_duckdb(sql, "snowflake")
    assert isinstance(statements, list)
    con = duckdb.connect()
    try:
        con.execute("CREATE SCHEMA raw")
        con.execute(
            'CREATE TABLE raw."table" ("order" INTEGER, region VARCHAR, amount INTEGER, '
            '"start" INTEGER)'
        )
        con.execute(
            """INSERT INTO raw."table" VALUES (1, 'eu', 150, 1), (1, 'eu', 50, 2), """
            """(2, 'us', NULL, 1)"""
        )
        for statement in statements:
            con.execute(statement)
        rows = con.execute("SELECT * FROM orders ORDER BY 1").fetchall()
    finally:
        con.close()
    assert [(key, region, band, float(amount)) for key, region, band, amount in rows] == [
        (1, "eu", "small", 50.0),
        (2, "us", "small", 0.0),
    ]


def _cases() -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    for group in (EXAMPLES, VALID):
        for template in subdirs(group):
            found.extend((template, case) for case in subdirs(template / "tests"))
    return found


@pytest.mark.parametrize(
    ("template_dir", "case"), _cases(), ids=lambda path: path.name if isinstance(path, Path) else ""
)
def test_every_example_renders_as_before(template_dir: Path, case: Path) -> None:
    # Each file under tests/fixtures/renders/ was written by the renderer before reserved
    # words were quoted (main at 694d590), from the case's own slot values.
    template = load_template(template_dir)
    values = load_yaml((case / "slots.yaml").read_text(encoding="utf-8"))
    assert isinstance(values, dict)
    suffix = ".py.txt" if template.language == "python" else ".sql.txt"
    before = RENDERS / template_dir.parent.name / template_dir.name / f"{case.name}{suffix}"
    assert render(template, values) == before.read_text(encoding="utf-8")
