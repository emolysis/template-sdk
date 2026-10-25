"""Reserved words per dialect, and how an identifier slot value is written in SQL.

Implements docs/format.md section 4 ("Identifiers and reserved words"), which is
normative; where this module disagrees with it, this module is wrong.

A name that its dialect reserves is written as a quoted identifier that names the same
object the unquoted word would: Snowflake stores and resolves an unquoted name in upper
case, so `order` is written `"ORDER"`; DuckDB matches names case-insensitively, so `order`
is written `"order"`. Any other name, and every name in a dialect without a list here, is
written verbatim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .reserved_duckdb import DUCKDB_RESERVED

SNOWFLAKE_SOURCE = "https://docs.snowflake.com/en/sql-reference/reserved-keywords"
"""Where the Snowflake list comes from: every keyword in the page's table."""

SNOWFLAKE_READ = "2026-10-25"
"""The date the Snowflake list was copied from its source."""

SNOWFLAKE_RESERVED: frozenset[str] = frozenset(
    {
        "ACCOUNT",
        "ALL",
        "ALTER",
        "AND",
        "ANY",
        "AS",
        "BETWEEN",
        "BY",
        "CASE",
        "CAST",
        "CHECK",
        "COLUMN",
        "CONNECT",
        "CONNECTION",
        "CONSTRAINT",
        "CREATE",
        "CROSS",
        "CURRENT",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "DATABASE",
        "DELETE",
        "DISTINCT",
        "DROP",
        "ELSE",
        "EXISTS",
        "FALSE",
        "FOLLOWING",
        "FOR",
        "FROM",
        "FULL",
        "GRANT",
        "GROUP",
        "GSCLUSTER",
        "HAVING",
        "ILIKE",
        "IN",
        "INCREMENT",
        "INNER",
        "INSERT",
        "INTERSECT",
        "INTO",
        "IS",
        "ISSUE",
        "JOIN",
        "LATERAL",
        "LEFT",
        "LIKE",
        "LOCALTIME",
        "LOCALTIMESTAMP",
        "MINUS",
        "NATURAL",
        "NOT",
        "NULL",
        "OF",
        "ON",
        "OR",
        "ORDER",
        "ORGANIZATION",
        "QUALIFY",
        "REGEXP",
        "REVOKE",
        "RIGHT",
        "RLIKE",
        "ROW",
        "ROWS",
        "SAMPLE",
        "SCHEMA",
        "SELECT",
        "SET",
        "SOME",
        "START",
        "TABLE",
        "TABLESAMPLE",
        "THEN",
        "TO",
        "TRIGGER",
        "TRUE",
        "TRY_CAST",
        "UNION",
        "UNIQUE",
        "UPDATE",
        "USING",
        "VALUES",
        "VIEW",
        "WHEN",
        "WHENEVER",
        "WHERE",
        "WINDOW",
        "WITH",
    }
)
"""Snowflake's reserved and limited keywords, as its documentation lists them."""

RESERVED: Mapping[str, frozenset[str]] = {
    "databricks": frozenset(),
    "duckdb": frozenset(word.lower() for word in DUCKDB_RESERVED),
    "snowflake": frozenset(word.lower() for word in SNOWFLAKE_RESERVED),
    "spark": frozenset(),
}
"""Each SQL dialect's reserved words in lower case. Databricks and Spark need none for
slot values (docs/format.md section 4)."""

_UNQUOTED_CASE: Mapping[str, Callable[[str], str]] = {"snowflake": str.upper}
"""The case a dialect stores an unquoted name in; a dialect not listed keeps the name."""


def write_identifier(name: str, dialect: str) -> str:
    """Write one plain identifier for `dialect`: quoted when the dialect reserves it.

    A quoted name is written in the case the dialect gives the unquoted name, so it names
    the same object. `name` must match `[A-Za-z_][A-Za-z0-9_]*`, so it never holds a quote.
    """
    if name.lower() not in RESERVED.get(dialect, frozenset()):
        return name
    case = _UNQUOTED_CASE.get(dialect)
    return f'"{case(name) if case is not None else name}"'


def write_table(name: str, dialect: str) -> str:
    """Write a table name of 1 to 3 parts, each part as `write_identifier` writes it."""
    return ".".join(write_identifier(part, dialect) for part in name.split("."))
