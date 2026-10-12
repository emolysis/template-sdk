CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT id, missing_column FROM {{ source_table }};
