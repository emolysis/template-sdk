CREATE OR REPLACE TABLE {{ target_table }}_copy AS
SELECT * FROM {{ source_table }};
