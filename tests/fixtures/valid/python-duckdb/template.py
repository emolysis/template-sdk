"""Test fixture: a Python entry that keeps distinct rows on DuckDB."""

SOURCE = {{ source_table }}
TARGET = {{ target_table }}
KEYS = {{ keys }}


def run(con):
    columns = ", ".join(KEYS)
    con.execute(f"CREATE OR REPLACE TABLE {TARGET} AS SELECT DISTINCT {columns} FROM {SOURCE}")
