SOURCE = {{ source_table }}
TARGET = {{ target_table }}


def main(con):
    con.execute(f"CREATE OR REPLACE TABLE {TARGET} AS SELECT * FROM {SOURCE}")
