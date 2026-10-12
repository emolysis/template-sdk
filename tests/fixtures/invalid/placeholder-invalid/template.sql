{% if incremental %}
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT * FROM {{ source_table }};
