"""Write or check every Parquet fixture in this repository.

Each table is defined here as a DuckDB query, so fixtures are reviewable as text and can
be regenerated. Expected tables are written by hand from the inputs, never by running
the template under test.

    uv run python scripts/make_fixtures.py          # write all fixtures
    uv run python scripts/make_fixtures.py --check  # compare committed files with this script

Every .parquet file under tests/fixtures/invalid/ and tests/fixtures/failing/ holds the
generic two-row table unless listed in NOT_PARQUET; copy a fixture directory to add one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "examples/aggregation-gold-duckdb/tests"
VALID = "tests/fixtures/valid"
GENERIC_ROOTS = ("tests/fixtures/invalid", "tests/fixtures/failing")
SCANNED_ROOTS = ("examples", "tests/fixtures")

NOT_PARQUET = {
    # Deliberately broken: the validator must report parquet-invalid for it.
    "tests/fixtures/invalid/parquet-invalid/tests/basic/runs/01/expected/target.parquet",
}

GENERIC = """
SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name
FROM (VALUES (1, 'a'), (2, 'b')) AS t(id, name)
"""


def _orders(rows: str) -> str:
    return f"""
SELECT
    CAST(order_id AS INTEGER) AS order_id,
    CAST(order_date AS DATE) AS order_date,
    CAST(region AS VARCHAR) AS region,
    CAST(channel AS VARCHAR) AS channel,
    CAST(status AS VARCHAR) AS status,
    CAST(amount AS DECIMAL(12, 2)) AS amount
FROM (VALUES {rows}) AS t(order_id, order_date, region, channel, status, amount)
"""


ORDERS_DAY_2 = """
    (1, '2026-10-01', 'north', 'web',   'paid',      120.00),
    (2, '2026-10-01', 'north', 'store', 'paid',       80.50),
    (3, '2026-10-01', 'south', 'web',   'paid',       42.25),
    (4, '2026-10-01', 'south', 'web',   'cancelled', 300.00),
    (5, '2026-10-02', 'north', 'web',   'paid',       15.00),
    (6, '2026-10-02', 'south', 'store', 'paid',       99.99),
    (7, '2026-10-02', 'south', 'web',   'paid',        0.01),
    (8, '2026-10-02', 'north', 'web',   'refunded',   60.00)
"""

# A later extract: order 3 was cancelled, order 11 arrived late for 2026-10-01 and two
# orders were placed on 2026-10-03.
ORDERS_DAY_3 = """
    (1,  '2026-10-01', 'north', 'web',   'paid',      120.00),
    (2,  '2026-10-01', 'north', 'store', 'paid',       80.50),
    (3,  '2026-10-01', 'south', 'web',   'cancelled',  42.25),
    (4,  '2026-10-01', 'south', 'web',   'cancelled', 300.00),
    (5,  '2026-10-02', 'north', 'web',   'paid',       15.00),
    (6,  '2026-10-02', 'south', 'store', 'paid',       99.99),
    (7,  '2026-10-02', 'south', 'web',   'paid',        0.01),
    (8,  '2026-10-02', 'north', 'web',   'refunded',   60.00),
    (9,  '2026-10-03', 'north', 'web',   'paid',       10.00),
    (10, '2026-10-03', 'north', 'store', 'paid',       20.00),
    (11, '2026-10-01', 'south', 'store', 'paid',        7.75)
"""


def _revenue(rows: str) -> str:
    return f"""
SELECT
    CAST(order_date AS DATE) AS order_date,
    CAST(region AS VARCHAR) AS region,
    CAST(order_count AS BIGINT) AS order_count,
    CAST(revenue AS DECIMAL(18, 2)) AS revenue
FROM (VALUES {rows}) AS t(order_date, region, order_count, revenue)
"""


def _by_channel(rows: str) -> str:
    return f"""
SELECT
    CAST(order_date AS DATE) AS order_date,
    CAST(region AS VARCHAR) AS region,
    CAST(channel AS VARCHAR) AS channel,
    CAST(row_count AS BIGINT) AS row_count,
    CAST(total_amount AS DECIMAL(18, 2)) AS total_amount,
    CAST(largest_amount AS DECIMAL(12, 2)) AS largest_amount
FROM (VALUES {rows}) AS t(order_date, region, channel, row_count, total_amount, largest_amount)
"""


TABLES: dict[str, str] = {
    # examples/aggregation-gold-duckdb, case known-totals: by day and region, cancelled
    # orders left out of both measures.
    f"{EXAMPLE}/known-totals/runs/01/input/orders.parquet": _orders(ORDERS_DAY_2),
    f"{EXAMPLE}/known-totals/runs/01/expected/daily_revenue.parquet": _revenue(
        """
        ('2026-10-01', 'north', 2, 200.50),
        ('2026-10-01', 'south', 1,  42.25),
        ('2026-10-02', 'north', 2,  75.00),
        ('2026-10-02', 'south', 2, 100.00)
        """
    ),
    f"{EXAMPLE}/known-totals/runs/02/input/orders.parquet": _orders(ORDERS_DAY_3),
    f"{EXAMPLE}/known-totals/runs/02/expected/daily_revenue.parquet": _revenue(
        """
        ('2026-10-01', 'north', 2, 200.50),
        ('2026-10-01', 'south', 1,   7.75),
        ('2026-10-02', 'north', 2,  75.00),
        ('2026-10-02', 'south', 2, 100.00),
        ('2026-10-03', 'north', 2,  30.00)
        """
    ),
    # Case by-channel: day, region and channel, every row included.
    f"{EXAMPLE}/by-channel/runs/01/input/sales.parquet": _orders(ORDERS_DAY_2),
    f"{EXAMPLE}/by-channel/runs/01/expected/daily_sales.parquet": _by_channel(
        """
        ('2026-10-01', 'north', 'web',   1, 120.00, 120.00),
        ('2026-10-01', 'north', 'store', 1,  80.50,  80.50),
        ('2026-10-01', 'south', 'web',   2, 342.25, 300.00),
        ('2026-10-02', 'north', 'web',   2,  75.00,  60.00),
        ('2026-10-02', 'south', 'store', 1,  99.99,  99.99),
        ('2026-10-02', 'south', 'web',   1,   0.01,   0.01)
        """
    ),
    # tests/fixtures/valid
    f"{VALID}/minimal/tests/basic/runs/01/input/source.parquet": GENERIC,
    f"{VALID}/minimal/tests/basic/runs/01/expected/target.parquet": GENERIC,
    f"{VALID}/python-databricks/tests/basic/runs/01/input/source.parquet": GENERIC,
    f"{VALID}/python-databricks/tests/basic/runs/01/expected/target.parquet": GENERIC,
    f"{VALID}/python-duckdb/tests/basic/runs/01/input/source.parquet": """
        SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name
        FROM (VALUES (1, 'a'), (1, 'a'), (2, 'b')) AS t(id, name)
    """,
    f"{VALID}/python-duckdb/tests/basic/runs/01/expected/target.parquet": GENERIC,
    f"{VALID}/databricks-sql/tests/basic/runs/01/input/orders.parquet": """
        SELECT CAST(order_id AS INTEGER) AS order_id, CAST(region AS VARCHAR) AS region,
               CAST(amount AS DECIMAL(10, 2)) AS amount
        FROM (VALUES (1, 'north', 150.00), (2, 'north', 20.00), (3, 'south', NULL),
                     (4, 'south', 100.00), (5, 'north', 300.00)) AS t(order_id, region, amount)
    """,
    f"{VALID}/databricks-sql/tests/basic/runs/01/expected/size_bands.parquet": """
        SELECT CAST(region AS VARCHAR) AS region, CAST(size_band AS VARCHAR) AS size_band,
               CAST(label AS VARCHAR) AS label,
               CAST(total_amount AS DECIMAL(18, 2)) AS total_amount
        FROM (VALUES ('north', 'large', 'north-2', 450.00), ('north', 'small', 'north-1', 20.00),
                     ('south', 'small', 'south-1', 0.00), ('south', 'large', 'south-1', 100.00))
             AS t(region, size_band, label, total_amount)
    """,
    f"{VALID}/snowflake-sql/tests/basic/runs/01/input/orders_raw.parquet": """
        SELECT CAST(order_id AS INTEGER) AS order_id, CAST(region AS VARCHAR) AS region,
               CAST(amount AS DECIMAL(10, 2)) AS amount,
               CAST(loaded_at AS TIMESTAMP) AS loaded_at
        FROM (VALUES (1, 'north', 150.00, '2026-10-01 10:00:00'),
                     (1, 'north', 155.00, '2026-10-01 12:00:00'),
                     (2, 'south', NULL, '2026-10-01 10:00:00'),
                     (3, 'south', 99.00, '2026-10-02 08:00:00'))
             AS t(order_id, region, amount, loaded_at)
    """,
    f"{VALID}/snowflake-sql/tests/basic/runs/01/expected/orders.parquet": """
        SELECT CAST(order_id AS INTEGER) AS order_id, CAST(region AS VARCHAR) AS region,
               CAST(size_band AS VARCHAR) AS size_band, CAST(amount AS DECIMAL(10, 2)) AS amount
        FROM (VALUES (1, 'north', 'large', 155.00), (2, 'south', 'small', 0.00),
                     (3, 'south', 'small', 99.00)) AS t(order_id, region, size_band, amount)
    """,
    f"{VALID}/fabric-sql/tests/basic/runs/01/input/people.parquet": """
        SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name
        FROM (VALUES (1, 'a'), (2, NULL)) AS t(id, name)
    """,
    f"{VALID}/fabric-sql/tests/basic/runs/01/expected/people_clean.parquet": """
        SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name,
               CAST(name_was_missing AS BOOLEAN) AS name_was_missing
        FROM (VALUES (1, 'a', false), (2, 'unknown', true)) AS t(id, name, name_was_missing)
    """,
    f"{VALID}/incremental-state/tests/overlap/runs/01/input/events.parquet": GENERIC,
    f"{VALID}/incremental-state/tests/overlap/runs/01/expected/events_all.parquet": GENERIC,
    f"{VALID}/incremental-state/tests/overlap/runs/02/input/events.parquet": """
        SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name
        FROM (VALUES (2, 'b'), (3, 'c')) AS t(id, name)
    """,
    f"{VALID}/incremental-state/tests/overlap/runs/02/expected/events_all.parquet": """
        SELECT CAST(id AS INTEGER) AS id, CAST(name AS VARCHAR) AS name
        FROM (VALUES (1, 'a'), (2, 'b'), (3, 'c')) AS t(id, name)
    """,
}


def _parquet_files(roots: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for root in roots:
        base = ROOT / root
        if base.is_dir():
            found.extend(p.relative_to(ROOT).as_posix() for p in base.rglob("*.parquet"))
    return sorted(found)


def plan() -> dict[str, str]:
    """Every fixture this script owns: relative path -> query that produces it."""
    planned = dict(TABLES)
    for rel in _parquet_files(GENERIC_ROOTS):
        if rel not in planned and rel not in NOT_PARQUET:
            planned[rel] = GENERIC
    return planned


def _literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def write(planned: dict[str, str]) -> None:
    with duckdb.connect(":memory:") as con:
        for rel, query in planned.items():
            path = ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY ({query}) TO {_literal(path)} (FORMAT parquet)")
            print(f"wrote {rel}")


def check(planned: dict[str, str]) -> list[str]:
    problems: list[str] = []
    with duckdb.connect(":memory:") as con:
        for rel, query in planned.items():
            path = ROOT / rel
            if not path.is_file():
                problems.append(f"{rel}: missing; run scripts/make_fixtures.py")
                continue
            stored = f"SELECT * FROM read_parquet({_literal(path)})"
            want = con.execute(f"DESCRIBE {query}").fetchall()
            have = con.execute(f"DESCRIBE {stored}").fetchall()
            if [row[:2] for row in want] != [row[:2] for row in have]:
                problems.append(f"{rel}: columns differ from the definition")
                continue
            for left, right in ((query, stored), (stored, query)):
                row = con.execute(
                    f"SELECT count(*) FROM (({left}) EXCEPT ALL ({right}))"
                ).fetchone()
                if row is None or row[0]:
                    problems.append(f"{rel}: rows differ from the definition")
                    break
    for rel in _parquet_files(SCANNED_ROOTS):
        if rel not in planned and rel not in NOT_PARQUET:
            problems.append(f"{rel}: not defined in scripts/make_fixtures.py")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args(argv)
    planned = plan()
    if not args.check:
        write(planned)
        return 0
    problems = check(planned)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"{len(planned)} fixtures match scripts/make_fixtures.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
