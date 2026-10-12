CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT * FROM {{ source_table }};

OPTIMIZE {{ target_table }};
