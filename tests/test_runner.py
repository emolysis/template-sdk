"""Local test runner on DuckDB."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import EXAMPLE, FAILING, INVALID, VALID, copy_fixture, subdirs
from emolysis_template_sdk import Problem, run_tests, transpile_to_duckdb
from emolysis_template_sdk.runner import type_family

FAILING_CODES = {
    "column-type-mismatch": "columns-mismatch",
    "columns-mismatch": "columns-mismatch",
    "python-run-missing": "python-run-missing",
    "rows-mismatch": "rows-mismatch",
    "run-failed": "run-failed",
    "table-missing": "table-missing",
    "transpile-command": "transpile-failed",
    "transpile-unsupported": "transpile-failed",
}


def test_example_passes() -> None:
    report = run_tests(EXAMPLE)
    assert report.ok
    assert report.template_id == "aggregation-gold.duckdb"
    assert [(c.name, c.status, c.runs_passed, c.runs_total) for c in report.cases] == [
        ("by-channel", "passed", 1, 1),
        ("known-totals", "passed", 2, 2),
    ]
    assert report.problems == ()


@pytest.mark.parametrize(
    "name",
    [
        "minimal",
        "databricks-sql",
        "snowflake-sql",
        "fabric-sql",
        "incremental-state",
        "python-duckdb",
    ],
)
def test_valid_fixtures_pass(name: str) -> None:
    report = run_tests(VALID / name)
    assert report.ok, report.to_dict()
    assert report.cases
    assert all(case.status == "passed" for case in report.cases)


def test_python_entry_for_a_platform_is_skipped() -> None:
    report = run_tests(VALID / "python-databricks")
    assert report.ok
    [case] = report.cases
    assert case.status == "skipped"
    assert [p.code for p in case.problems] == ["python-entry-skipped"]
    assert case.problems[0].severity == "warning"


def test_state_carries_across_runs() -> None:
    [case] = run_tests(VALID / "incremental-state").cases
    assert (case.status, case.runs_passed, case.runs_total) == ("passed", 2, 2)


@pytest.mark.parametrize("fixture", subdirs(FAILING), ids=lambda p: p.name)
def test_failing_fixtures(fixture: Path) -> None:
    report = run_tests(fixture)
    assert not report.ok
    [case] = report.cases
    assert case.status == "failed"
    assert [p.code for p in case.problems] == [FAILING_CODES[fixture.name]]


def test_failing_fixture_table_is_complete() -> None:
    assert set(FAILING_CODES) == {p.name for p in subdirs(FAILING)}


def test_rows_mismatch_shows_sample_rows() -> None:
    [case] = run_tests(FAILING / "rows-mismatch").cases
    message = case.problems[0].message
    assert "1 row missing, 0 rows unexpected" in message
    assert "missing: (2, 'b')" in message
    assert case.problems[0].path == "tests/basic/runs/01/expected/target.parquet"


def test_invalid_template_does_not_run() -> None:
    report = run_tests(INVALID / "slot-missing")
    assert not report.ok
    assert report.template_id is None
    assert report.cases == ()
    assert {p.code for p in report.problems} == {"slot-missing"}


def test_later_run_failure_counts_passed_runs(tmp_path: Path) -> None:
    template = copy_fixture(VALID / "incremental-state", tmp_path)
    expected = template / "tests/overlap/runs/02/expected/events_all.parquet"
    first = template / "tests/overlap/runs/01/expected/events_all.parquet"
    expected.write_bytes(first.read_bytes())
    [case] = run_tests(template).cases
    assert (case.status, case.runs_passed) == ("failed", 1)
    assert [p.code for p in case.problems] == ["rows-mismatch"]


def test_corrupt_parquet_is_reported(minimal: Path) -> None:
    source = minimal / "tests/basic/runs/01/input/source.parquet"
    source.write_bytes(b"PAR1" + b"\x00" * 32 + b"PAR1")
    [case] = run_tests(minimal).cases
    assert [p.code for p in case.problems] == ["input-unreadable"]


def test_extra_column_and_unexpected_rows(minimal: Path) -> None:
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT *, 1 AS extra FROM {{ source_table }};\n"
    )
    [case] = run_tests(minimal).cases
    assert "unexpected columns extra" in case.problems[0].message
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT * FROM {{ source_table }} UNION ALL SELECT 3, 'c';\n"
    )
    [case] = run_tests(minimal).cases
    assert "0 rows missing, 1 row unexpected" in case.problems[0].message


def test_row_order_is_ignored_and_duplicates_count(minimal: Path) -> None:
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT * FROM {{ source_table }} ORDER BY id DESC;\n"
    )
    assert run_tests(minimal).ok
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT * FROM {{ source_table }} UNION ALL SELECT * FROM {{ source_table }};\n"
    )
    assert not run_tests(minimal).ok


def test_python_entry_errors_are_reported(minimal: Path) -> None:
    (minimal / "template.sql").unlink()
    manifest = minimal / "template.yaml"
    manifest.write_text(manifest.read_text().replace("template.sql", "template.py"))
    (minimal / "template.py").write_text(
        "S = {{ source_table }}\nT = {{ target_table }}\n\n\ndef run(con):\n"
        "    raise RuntimeError('boom')\n"
    )
    [case] = run_tests(minimal).cases
    assert [p.code for p in case.problems] == ["run-failed"]
    assert "boom" in case.problems[0].message
    (minimal / "template.py").write_text(
        "import sys\nS = {{ source_table }}\nT = {{ target_table }}\nsys.exit(3)\n"
    )
    [case] = run_tests(minimal).cases
    assert [p.code for p in case.problems] == ["run-failed"]


def test_transpile_to_duckdb() -> None:
    statements = transpile_to_duckdb(
        "SELECT `a`, nvl(b, 0) FROM t; SELECT IF(x, 1, 2) FROM u", "databricks"
    )
    assert statements == [
        'SELECT "a", COALESCE(b, 0) FROM t',
        "SELECT CASE WHEN x THEN 1 ELSE 2 END FROM u",
    ]
    problem = transpile_to_duckdb("SELECT FROM WHERE", "databricks", "template.sql")
    assert isinstance(problem, Problem)
    assert problem.code == "transpile-failed"
    assert problem.path == "template.sql"


@pytest.mark.parametrize(
    ("duckdb_type", "family"),
    [
        ("INTEGER", "exact-number"),
        ("HUGEINT", "exact-number"),
        ("DECIMAL(18,2)", "exact-number"),
        ("DOUBLE", "approximate-number"),
        ("VARCHAR", "string"),
        ("DATE", "date"),
        ("TIMESTAMP", "timestamp"),
        ("TIMESTAMP_NS", "timestamp"),
        ("TIMESTAMP WITH TIME ZONE", "timestamptz"),
        ("TIME", "time"),
        ("INTEGER[]", "nested"),
        ("STRUCT(a INTEGER)", "nested"),
        ("BOOLEAN", "boolean"),
        ("BLOB", "blob"),
    ],
)
def test_type_family(duckdb_type: str, family: str) -> None:
    assert type_family(duckdb_type) == family


def test_report_to_dict() -> None:
    data = run_tests(VALID / "minimal").to_dict()
    assert data["ok"] is True
    assert data["template_id"] == "snapshot.duckdb"
    assert isinstance(data["cases"], list)


def test_incomparable_values_are_reported(minimal: Path) -> None:
    import duckdb

    expected = minimal / "tests/basic/runs/01/expected/target.parquet"
    with duckdb.connect() as con:
        con.execute(f"COPY (SELECT 1 AS id, [1, 2] AS name) TO '{expected}' (FORMAT parquet)")
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT id, {'a': 1} AS name FROM {{ source_table }};\n"
    )
    [case] = run_tests(minimal).cases
    assert [p.code for p in case.problems] == ["compare-failed"]
