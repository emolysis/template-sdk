CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT CAST(id AS VARCHAR) AS id, name FROM {{ source_table }};
