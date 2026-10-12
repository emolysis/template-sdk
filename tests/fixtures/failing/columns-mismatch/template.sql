CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT id FROM {{ source_table }};
