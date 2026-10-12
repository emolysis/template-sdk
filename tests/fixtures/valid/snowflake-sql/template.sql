-- Snowflake SQL that needs transpiling: IFF, ZEROIFNULL, :: casts and QUALIFY.
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT
  {{ key_column }},
  region,
  IFF(ZEROIFNULL(amount) >= 100, 'large', 'small') AS size_band,
  ZEROIFNULL(amount)::NUMBER(10, 2) AS amount
FROM {{ source_table }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY {{ key_column }} ORDER BY {{ loaded_at }} DESC) = 1;
