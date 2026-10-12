-- Spark SQL that needs transpiling: backticks, IF, nvl, STRING and concat_ws, in the
-- entry and in the measures.
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT
  {{ group_by }},
  {{ measures }}
FROM (
  SELECT *, IF(nvl(amount, 0) >= {{ large_threshold }}, 'large', 'small') AS size_band
  FROM {{ source_table }}
) AS banded
GROUP BY {{ group_by }};
