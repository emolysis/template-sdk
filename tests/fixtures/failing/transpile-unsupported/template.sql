CREATE OR REPLACE TABLE {{ target_table }}
USING delta
CLUSTER BY (id)
AS SELECT * FROM {{ source_table }};
