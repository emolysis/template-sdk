-- Spark SQL for a Fabric lakehouse: backticks, nvl and IF.
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT
  `id`,
  nvl(`name`, {{ fallback_name }}) AS name,
  IF(`name` IS NULL, true, false) AS name_was_missing
FROM {{ source_table }};
