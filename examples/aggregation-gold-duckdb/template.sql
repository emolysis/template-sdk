-- Aggregation / gold on DuckDB: rebuild a gold table with one row per group.
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT
    {{ group_by }},
    {{ measures }}
FROM {{ source_table }}
GROUP BY {{ group_by }};
