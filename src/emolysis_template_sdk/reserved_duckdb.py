"""DuckDB's reserved keywords, written by scripts/make_reserved_words.py; do not edit.

The `reserved` category of `duckdb_keywords()` in DuckDB 1.5.6, read 2026-10-25.
DuckDB documents the function and the categories at
https://duckdb.org/docs/stable/sql/dialect/keywords_and_identifiers.
"""

from __future__ import annotations

DUCKDB_VERSION = "1.5.6"
"""The DuckDB version the list was read from."""

DUCKDB_READ = "2026-10-25"
"""The date the list was read."""

DUCKDB_RESERVED: frozenset[str] = frozenset(
    {
        "all",
        "analyse",
        "analyze",
        "and",
        "any",
        "array",
        "as",
        "asc",
        "asymmetric",
        "both",
        "case",
        "cast",
        "check",
        "collate",
        "column",
        "constraint",
        "create",
        "default",
        "deferrable",
        "desc",
        "describe",
        "distinct",
        "do",
        "else",
        "end",
        "except",
        "false",
        "fetch",
        "for",
        "foreign",
        "from",
        "group",
        "having",
        "in",
        "initially",
        "intersect",
        "into",
        "lambda",
        "lateral",
        "leading",
        "limit",
        "not",
        "null",
        "offset",
        "on",
        "only",
        "or",
        "order",
        "pivot",
        "pivot_longer",
        "pivot_wider",
        "placing",
        "primary",
        "qualify",
        "references",
        "returning",
        "select",
        "show",
        "some",
        "summarize",
        "symmetric",
        "table",
        "then",
        "to",
        "trailing",
        "true",
        "union",
        "unique",
        "unpivot",
        "using",
        "variadic",
        "when",
        "where",
        "window",
        "with",
    }
)
"""DuckDB's reserved keywords, in lower case as DuckDB lists them."""
