CREATE TABLE IF NOT EXISTS {{ target_table }} AS
SELECT * FROM {{ source_table }} WHERE FALSE;

INSERT INTO {{ target_table }}
SELECT s.*
FROM {{ source_table }} AS s
WHERE NOT EXISTS (
  SELECT 1 FROM {{ target_table }} AS t WHERE t.{{ key_column }} = s.{{ key_column }}
);
