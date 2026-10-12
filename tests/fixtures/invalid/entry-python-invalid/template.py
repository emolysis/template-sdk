SOURCE = {{ source_table }}
TARGET = {{ target_table }}


def run(con)
    con.execute(f"CREATE OR REPLACE TABLE {TARGET} AS SELECT * FROM {SOURCE}")
