"""Fixed vocabulary of template format v0: shapes, platforms, dialects, slot types.

Everything here is normative and mirrors docs/format.md. Changing a value is a format
change and needs a docs/format.md changelog entry.
"""

from __future__ import annotations

import re
from typing import Final

FORMAT_V0: Final = "emolysis.template/v0"
"""Value of the `format` field for templates in this format version."""

FORMAT_PREFIX: Final = "emolysis.template/"

SHAPES: Final[dict[str, str]] = {
    "ingest-batch": "Ingest (batch)",
    "incremental-append": "Incremental append",
    "cdc-merge": "CDC merge",
    "scd2": "SCD Type 2",
    "snapshot": "Snapshot",
    "backfill": "Backfill",
    "late-arriving": "Late-arriving",
    "dedupe-conform": "Dedupe / conform",
    "aggregation-gold": "Aggregation / gold",
    "reverse-etl": "Reverse ETL",
}
"""Pipeline shape id -> display name."""

PLATFORMS: Final[dict[str, str]] = {
    "databricks": "Databricks",
    "snowflake": "Snowflake",
    "fabric": "Microsoft Fabric",
    "duckdb": "DuckDB",
}
"""Platform id -> display name. `duckdb` is for local-only templates."""

LOCAL_PLATFORM: Final = "duckdb"

DIALECTS: Final[dict[str, str]] = {
    "databricks": "databricks",
    "snowflake": "snowflake",
    "fabric": "spark",
    "duckdb": "duckdb",
}
"""Platform id -> SQLGlot dialect the entry file is written in."""

SLOT_TYPES: Final = (
    "identifier",
    "table",
    "column",
    "columns",
    "expression",
    "expressions",
    "string",
    "integer",
    "boolean",
    "duration",
    "enum",
)

ENTRY_FILES: Final[dict[str, str]] = {"template.sql": "sql", "template.py": "python"}
"""Allowed entry file names -> entry language."""

MANIFEST_FILE: Final = "template.yaml"
COST_FILE: Final = "cost.md"
CONSTRAINTS_FILE: Final = "profile_constraints.json"
TESTS_DIR: Final = "tests"
CASE_SLOTS_FILE: Final = "slots.yaml"
RUNS_DIR: Final = "runs"
INPUT_DIR: Final = "input"
EXPECTED_DIR: Final = "expected"

IDENTIFIER_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
"""A plain, unquoted SQL identifier (identifier, column and table-part slots, table files)."""

TABLE_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2}")
"""One to three dot-separated identifiers: table, schema.table or catalog.schema.table."""

SLOT_NAME_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
CASE_NAME_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
RUN_NAME_RE: Final = re.compile(r"[0-9]{2}")
ENUM_VALUE_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SEMVER_RE: Final = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)

DURATION_RE: Final = re.compile(
    r"\s*([0-9]{1,9})\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours"
    r"|d|day|days|w|week|weeks)\s*",
    re.IGNORECASE,
)

DURATION_UNITS: Final[dict[str, tuple[str, int]]] = {
    "s": ("SECOND", 1),
    "sec": ("SECOND", 1),
    "secs": ("SECOND", 1),
    "second": ("SECOND", 1),
    "seconds": ("SECOND", 1),
    "m": ("MINUTE", 60),
    "min": ("MINUTE", 60),
    "mins": ("MINUTE", 60),
    "minute": ("MINUTE", 60),
    "minutes": ("MINUTE", 60),
    "h": ("HOUR", 3600),
    "hr": ("HOUR", 3600),
    "hrs": ("HOUR", 3600),
    "hour": ("HOUR", 3600),
    "hours": ("HOUR", 3600),
    "d": ("DAY", 86400),
    "day": ("DAY", 86400),
    "days": ("DAY", 86400),
    "w": ("WEEK", 604800),
    "week": ("WEEK", 604800),
    "weeks": ("WEEK", 604800),
}
"""Duration unit spelling (lower case) -> (SQL interval unit, seconds per unit)."""


def template_id(shape: str, platform: str) -> str:
    """Return the template id for a shape and platform: `<shape>.<platform>`."""
    return f"{shape}.{platform}"
