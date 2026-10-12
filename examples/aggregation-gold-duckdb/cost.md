# Cost notes: Gold aggregate on DuckDB

- Runs locally; there is no platform bill.
- One full scan of the source table per run, then a hash aggregation. Memory grows with
  the number of distinct `group_by` combinations, not with the number of source rows.
- The target is rebuilt on every run, so cost grows with the whole source, not with what
  changed since the last run. For large histories, aggregate a date window into a
  separate target and keep older periods in their own table.
- Measures with `FILTER` or `CASE` cost about the same as plain aggregates; distinct
  counts (`count(DISTINCT x)`) need memory per group.
