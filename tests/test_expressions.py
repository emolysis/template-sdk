"""The `expressions` slot type: value checks, SQL and Python rendering, local runs."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest
import yaml

from conftest import EXAMPLE, VALID
from emolysis_template_sdk import DIALECTS, Slot, load_template, render, run_tests, validate
from emolysis_template_sdk.slots import (
    check_select_item,
    check_value,
    normalize_select_item,
    render_value,
)

SLOT = Slot(name="measures", type="expressions", required=True)
ENGINE_DIALECTS = sorted(set(DIALECTS.values()))

GOOD: list[list[str]] = [
    ["count(*)"],
    ["count(*) AS orders", "sum(amount) AS revenue"],
    ["sum(amount) revenue"],
    ["count(*) FILTER (WHERE status <> 'cancelled') AS orders"],
    ["row_number() OVER (PARTITION BY region ORDER BY amount DESC) AS rank"],
    ["(SELECT max(id) FROM t) AS top_id"],
    ["CASE WHEN amount > 100 THEN 'large' ELSE 'small' END AS band"],
    ["sum(amount) AS total -- trailing comment"],
    ["concat(region, ', ', channel) AS label"],
    ["region", "*"],
]

BAD: list[object] = [
    [],
    "count(*)",
    None,
    {"count": "*"},
    [""],
    ["   "],
    [1],
    [None],
    [["count(*)"]],
    ["a, b"],
    ["x FROM t"],
    ["x WHERE y"],
    ["DISTINCT x"],
    ["SELECT 1"],
    ["x AS y AS z"],
    ["1; DROP TABLE x"],
    ["'a;b'"],
    ["(("],
    ["count(*)", "sum(amount) FROM t"],
]


@pytest.mark.parametrize("value", GOOD)
def test_good_values(value: list[str]) -> None:
    assert check_value(SLOT, value, "duckdb") is None


@pytest.mark.parametrize("value", BAD)
def test_bad_values(value: object) -> None:
    assert check_value(SLOT, value, "duckdb") is not None


def test_problem_names_the_item() -> None:
    reason = check_value(SLOT, ["count(*) AS n", "x FROM t"], "duckdb")
    assert reason is not None
    assert reason.startswith("item 2: ")


@pytest.mark.parametrize("dialect", ["databricks", "spark"])
@pytest.mark.parametrize("item", [":`'`", ":`:`"])
def test_an_item_whose_written_form_does_not_parse_is_refused(dialect: str, item: str) -> None:
    # SQLGlot reads these and writes `:'` and `::`, which it cannot read back (found by
    # test_fuzz.py), so the item could not render.
    reason = check_value(SLOT, [item], dialect)
    assert reason is not None
    assert "does not parse" in reason


def test_items_are_checked_in_the_template_dialect() -> None:
    assert check_value(SLOT, ["`region`"], "databricks") is None
    assert check_value(SLOT, ["`region`"], "duckdb") is not None
    assert check_value(SLOT, ["IFF(a, 1, 2) AS f"], "snowflake") is None


@pytest.mark.parametrize(
    ("dialect", "items", "expected"),
    [
        (
            "duckdb",
            ["count(*) AS orders", "sum(amount)   revenue", "max(amount) -- largest"],
            "COUNT(*) AS orders, SUM(amount) AS revenue, MAX(amount)",
        ),
        (
            "duckdb",
            ["count(*) FILTER (WHERE status <> 'cancelled') AS n", "'it''s' AS q"],
            "COUNT(*) FILTER(WHERE status <> 'cancelled') AS n, 'it''s' AS q",
        ),
        (
            "databricks",
            ["`region` AS r", 'sum(amount) AS "Total"', "'it\\'s' AS q"],
            "`region` AS r, SUM(amount) AS `Total`, 'it\\'s' AS q",
        ),
        (
            "spark",
            ["IF(amount >= 100, 'large', 'small') AS band"],
            "IF(amount >= 100, 'large', 'small') AS band",
        ),
        (
            "snowflake",
            ["IFF(amount >= 100, 'large', 'small') AS band", "'it''s' AS q"],
            "IFF(amount >= 100, 'large', 'small') AS band, 'it\\'s' AS q",
        ),
    ],
)
def test_sql_rendering_normalizes_each_item_for_the_dialect(
    dialect: str, items: list[str], expected: str
) -> None:
    assert check_value(SLOT, items, dialect) is None
    assert render_value(SLOT, items, "sql", dialect) == expected


def test_python_rendering_is_a_list_of_the_strings_as_given() -> None:
    items = ["count(*) AS n", "sum(x)  -- kept as written"]
    text = render_value(SLOT, items, "python", "duckdb")
    assert text == repr(items)
    namespace: dict[str, object] = {}
    exec(compile(f"VALUE = {text}\n", "t.py", "exec"), namespace)
    assert namespace["VALUE"] == items


def test_normalize_rejects_what_check_rejects() -> None:
    assert check_select_item("x FROM t", "duckdb") is not None
    with pytest.raises(ValueError, match="not a list or a clause"):
        normalize_select_item("x FROM t", "duckdb")


@pytest.mark.parametrize("dialect", ENGINE_DIALECTS)
def test_normalized_items_are_valid_and_stable(dialect: str) -> None:
    for item in ["count(*) AS n", "sum(a) b", "coalesce(max(a), 0) AS m", "region"]:
        once = normalize_select_item(item, dialect)
        assert check_select_item(once, dialect) is None
        assert normalize_select_item(once, dialect) == once


def _write_manifest(root: Path, change: dict[str, object]) -> None:
    path = root / "template.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest.update(change)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))


def test_validate_checks_case_values_and_defaults(tmp_path: Path) -> None:
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    slots_file = root / "tests" / "known-totals" / "slots.yaml"
    values = yaml.safe_load(slots_file.read_text())
    values["measures"] = ["count(*) AS n", "amount FROM orders"]
    slots_file.write_text(yaml.safe_dump(values))
    problems = validate(root)
    assert [p.code for p in problems] == ["slot-value-invalid"]
    assert "measures: item 2:" in problems[0].message

    manifest = yaml.safe_load((root / "template.yaml").read_text())
    for slot in manifest["slots"]:
        if slot["name"] == "measures":
            slot.pop("required")
            slot["default"] = "count(*)"
    _write_manifest(root, {"slots": manifest["slots"]})
    codes = [p.code for p in validate(root)]
    assert "slot-default-invalid" in codes


def test_render_example_measures() -> None:
    template = load_template(EXAMPLE)
    assert [(s.name, s.type) for s in template.slots] == [
        ("source_table", "table"),
        ("target_table", "table"),
        ("group_by", "columns"),
        ("measures", "expressions"),
    ]
    rendered = render(
        template,
        {
            "source_table": "orders",
            "target_table": "daily",
            "group_by": ["order_date", "region"],
            "measures": ["count(*) AS orders", "sum(amount) revenue"],
        },
    )
    assert "    order_date, region,\n    COUNT(*) AS orders, SUM(amount) AS revenue\n" in rendered
    assert "GROUP BY order_date, region;" in rendered


def test_databricks_fixture_runs_transpiled_measures() -> None:
    template = load_template(VALID / "databricks-sql")
    assert template.slot("measures") is not None
    report = run_tests(VALID / "databricks-sql")
    assert report.ok, report.to_dict()


def test_snowflake_measures_run_on_duckdb(tmp_path: Path) -> None:
    root = tmp_path / "snowflake-measures"
    run = root / "tests" / "basic" / "runs" / "01"
    (run / "input").mkdir(parents=True)
    (run / "expected").mkdir(parents=True)
    (root / "template.yaml").write_text(
        "format: emolysis.template/v0\nid: aggregation-gold.snowflake\n"
        "shape: aggregation-gold\nplatform: snowflake\nversion: 0.1.0\n"
        "title: Measures on Snowflake\ndescription: Test.\nentry: template.sql\nslots:\n"
        "  - {name: source_table, type: table, required: true}\n"
        "  - {name: target_table, type: table, required: true}\n"
        "  - {name: group_by, type: columns, required: true}\n"
        "  - {name: measures, type: expressions, required: true}\n"
    )
    (root / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT {{ group_by }}, {{ measures }}\nFROM {{ source_table }}\n"
        "GROUP BY {{ group_by }};\n"
    )
    (root / "cost.md").write_text("Test.\n")
    (root / "profile_constraints.json").write_text(
        '{"platform": "snowflake", "profile_version": ">=1", "requires": [], "forbids": []}'
    )
    (root / "tests" / "basic" / "slots.yaml").write_text(
        "source_table: orders\ntarget_table: totals\ngroup_by: [region]\nmeasures:\n"
        "  - COUNT_IF(status = 'paid') AS paid_orders\n"
        "  - SUM(ZEROIFNULL(amount))::NUMBER(18, 2) AS revenue\n"
        "  - MAX(IFF(amount >= 100, 'large', 'small')) AS largest_band\n"
    )
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT * FROM (VALUES (1, 'north', 'paid', 150.00::DECIMAL(10, 2)),"
            " (2, 'north', 'cancelled', 20.00), (3, 'south', 'paid', NULL))"
            " AS t(order_id, region, status, amount))"
            f" TO '{run / 'input' / 'orders.parquet'}' (FORMAT parquet)"
        )
        con.execute(
            "COPY (SELECT * FROM (VALUES ('north', 1::BIGINT, 170.00::DECIMAL(18, 2), 'small'),"
            " ('south', 1, 0.00, 'small')) AS t(region, paid_orders, revenue, largest_band))"
            f" TO '{run / 'expected' / 'totals.parquet'}' (FORMAT parquet)"
        )
    assert validate(root) == []
    report = run_tests(root)
    assert report.ok, report.to_dict()
