# Writing templates

A guide for template authors. The rules are in [format.md](format.md); this document is
about doing it well. The running example is
[examples/aggregation-gold-duckdb](../examples/aggregation-gold-duckdb).

## 1. Pick one shape and one platform

A template is one shape on one platform: `scd2.databricks`, `cdc-merge.snowflake`,
`aggregation-gold.duckdb`. If the same logic should run on two platforms, write two
templates; their tests can share fixtures.

The shape table in [format.md](format.md#shapes) says what the golden tests for each
shape should cover, for example "attribute change across 3 runs" for `scd2`. Plan the
test cases before the SQL.

## 2. Start from a skeleton

```sh
emo-template new aggregation-gold duckdb my-daily-metrics
emo-template test my-daily-metrics      # passes: the skeleton copies source to target
```

The skeleton is valid and its one test passes, so every later failure is yours. Edit in
small steps and re-run `emo-template test` after each.

## 3. Write the entry file

Write the entry in the platform's dialect: Spark SQL for `databricks` and `fabric`,
Snowflake SQL for `snowflake`, DuckDB SQL for `duckdb`. Put everything that changes
between uses into slots and keep the logic fixed.

```sql
CREATE OR REPLACE TABLE {{ target_table }} AS
SELECT
    {{ group_by }},
    {{ measures }}
FROM {{ source_table }}
GROUP BY {{ group_by }};
```

With `group_by: [order_date, region]` and
`measures: [count(*) AS order_count, sum(amount) AS revenue]` this renders as:

```sql
CREATE OR REPLACE TABLE daily_revenue AS
SELECT
    order_date, region,
    COUNT(*) AS order_count, SUM(amount) AS revenue
FROM orders
GROUP BY order_date, region;
```

Guidelines:

- Make runs repeatable. Running a template twice on the same input should give the same
  result: `CREATE OR REPLACE` for full rebuilds, `MERGE` or anti-joins for incremental
  shapes, never a blind `INSERT` of everything.
- Stateful shapes create their target on first use (`CREATE TABLE IF NOT EXISTS ...`) and
  update it on later runs. The test runner keeps state between runs of a case, so this is
  testable.
- Keep output column names predictable: fixed in the template, or named by the caller
  through slot values (the `columns` of a `group_by`, the aliases of `expressions` items),
  so callers and tests can rely on them.
- There are no conditionals. If two variants differ in more than a value, write two
  templates.
- Keep platform-only statements (`OPTIMIZE`, `VACUUM`, table properties) out of templates
  for now: they cannot run in local tests (see [ROADMAP.md](../ROADMAP.md)).

## 4. Declare slots

Use the narrowest type that fits; the validator checks values for you.

| You need                    | Use           | Example value              |
| --------------------------- | ------------- | -------------------------- |
| a table to read or write    | `table`       | `silver.orders`            |
| one column                  | `column`      | `ordered_at`               |
| a key or grouping list      | `columns`     | `[region, channel]`        |
| a filter or computed value  | `expression`  | `status <> 'cancelled'`    |
| a select list or measures   | `expressions` | `[sum(amount) AS revenue]` |
| a literal text value        | `string`      | `EUR`                      |
| a count or limit            | `integer`     | `30`                       |
| a switch rendered as a word | `enum`        | `DESC` from `[ASC, DESC]`  |
| a time window               | `duration`    | `2 days`                   |
| a flag                      | `boolean`     | `true`                     |

- Required slots are things only the caller knows (table names, keys). Everything with a
  sensible default gets `default:` instead of `required: true`.
- Write a `description` for every slot. It is what a person or an agent filling the
  template reads.
- `string` values render as quoted literals, so do not put quotes around `{{ currency }}`
  in the SQL. `enum` values render verbatim, which suits keywords such as sort
  directions or join types.
- An `expression` default must be valid SQL in the dialect; quote it in YAML when it would
  otherwise read as a boolean or number (`default: "TRUE"`).
- Give every `expressions` item an alias (`sum(amount) AS revenue`): the alias becomes the
  output column name, and without one the name is whatever the engine makes up. Items are
  rewritten by SQLGlot for the dialect when rendered (format.md section 4), so write them
  in the platform's dialect like the rest of the entry. A filter that applies to one
  measure goes in the item: `count(*) FILTER (WHERE status <> 'cancelled') AS orders`.

## 5. Write `cost.md` and `profile_constraints.json`

`cost.md` tells the reader what running the template costs on its platform: the compute it
needs (warehouse size, cluster type), how cost grows (full scan per run, only new data,
one sort), and the settings that change it. Short and concrete beats long.

`profile_constraints.json` lists the platform features the template depends on, for
example `"requires": ["delta"]` for a Databricks template that uses `MERGE INTO` on Delta
tables. Use lower-case feature names.

## 6. Design test cases

Each case is a directory under `tests/` with a `slots.yaml` and numbered runs. Good cases
are small (a handful of rows), hand-checked and aimed at one behavior each:

- the main path with known results ("known totals" for the example);
- the edge the shape exists for: late rows, deletes, duplicates, a gap, a second
  snapshot;
- a case that exercises non-default slot values.

The example's `known-totals` case has two runs: run 01 is the first extract of `orders`;
run 02 is a later extract where one order was cancelled after the fact, one arrived late
for an earlier day and two new orders were placed. Its measures leave cancelled orders
out. Because the template rebuilds the target, run 02's expected table reflects all of
that.

Remember how runs work (format.md section 8): each run's `input/` tables replace tables of
the same name; everything else, including the template's outputs, carries over. After each
run every table in `expected/` must match.

Tips:

- Give `table` slots unqualified names in `slots.yaml` (`orders`, not `sales.orders`); the
  runner reads outputs from DuckDB's default schema.
- Store money and other fractions as `DECIMAL`; floating-point values compare exactly.
- Include `NULL`s where the real data has them.
- Write expected tables from the inputs by hand (or with an independent query), never by
  running the template you are testing and saving its output.

## 7. Make the Parquet files

Any tool that writes Parquet works. DuckDB is the simplest, and keeping the queries in a
script makes fixtures reviewable and reproducible:

```python
import duckdb

run = "my-daily-metrics/tests/known-totals/runs/01"
duckdb.sql(f"""
    COPY (
        SELECT CAST(order_id AS INTEGER) AS order_id,
               CAST(order_date AS DATE) AS order_date,
               CAST(region AS VARCHAR) AS region,
               CAST(amount AS DECIMAL(12, 2)) AS amount
        FROM (VALUES (1, '2026-10-01', 'north', 120.00),
                     (2, '2026-10-01', 'north',  80.50))
             AS t(order_id, order_date, region, amount)
    ) TO '{run}/input/orders.parquet' (FORMAT parquet)
""")
```

This repository's own fixtures are made this way by
[scripts/make_fixtures.py](../scripts/make_fixtures.py).

## 8. Validate and test

```sh
emo-template validate my-daily-metrics
emo-template test my-daily-metrics
```

`emo-template test` executes the template's SQL and Python on your machine with your
privileges; run it only on templates you trust. `validate` never executes them.

Failures name the file and the rule:

```
my-daily-metrics (aggregation-gold.duckdb)
  FAIL  known-totals  (1/2 runs)
        tests/known-totals/runs/02/expected/daily_revenue.parquet: error[rows-mismatch] table daily_revenue: 1 row missing, 1 row unexpected
            missing: (2026-10-01, 'south', 1, 7.75)
            unexpected: (2026-10-01, 'south', 2, 50.00)
```

`(1/2 runs)` means run 01 passed and run 02 failed. The full list of problem codes is in
[format.md](format.md#9-problem-codes). Use `--json` when another program reads the
output.

## 9. Platform notes

Templates for `databricks`, `snowflake` and `fabric` are tested locally by transpiling
them to DuckDB with SQLGlot. That catches logic errors early, but it is not a run on the
platform.

- **Databricks and Fabric (Spark SQL).** Backticks, `IF`, `nvl`, `QUALIFY` and most
  functions transpile. `date_add` on a `DATE` comes back as a `TIMESTAMP` on DuckDB; cast
  the result (`CAST(date_add(d, 1) AS DATE)`). Table properties (`USING delta`,
  `CLUSTER BY`) and maintenance statements cannot be transpiled.
- **Snowflake.** `IFF`, `ZEROIFNULL`, `::` casts and `QUALIFY` transpile. `DATEADD`
  returns a timestamp locally, as above. `TO_VARCHAR` with a format string cannot be
  transpiled. Unquoted identifiers are upper-cased by Snowflake but not by DuckDB. A slot
  value that Snowflake reserves, such as `order`, is written quoted in upper case
  (`"ORDER"`); write your own names in the entry file in lower case and unquoted.
- **Fabric warehouses (T-SQL)** cannot be expressed in v0; `fabric` templates are Spark SQL.
- **DuckDB** templates run as written.

When a construct does not transpile, the case fails with `transpile-failed` and names the
statement. Rewrite it in a portable form when one exists.

## 10. Python entries

Use `template.py` when SQL is not enough. Slot values render as Python literals
(the file below is a template, not Python, until it is rendered):

```text
SOURCE = {{ source_table }}      # renders as 'orders'
KEYS = {{ keys }}                # renders as ['id', 'name']


def run(con):
    columns = ", ".join(KEYS)
    con.execute(f"CREATE OR REPLACE TABLE deduped AS SELECT DISTINCT {columns} FROM {SOURCE}")
```

The runner calls `run(con)` with a DuckDB connection once per run, for platform `duckdb`
only; Python entries for other platforms are compiled but their tests are skipped with a
warning. Beware of f-string braces: `{{` starts a slot reference in v0, so write
`"{" "{"` if you need a literal `{{`.

## Checklist

- [ ] `emo-template validate` reports nothing.
- [ ] `emo-template test` passes every case, including at least one multi-run case for
      stateful shapes.
- [ ] Every slot has a description; only caller-specific slots are required.
- [ ] `cost.md` says what drives cost on the platform.
- [ ] Expected tables were computed independently of the template.
- [ ] `version` bumped according to [format.md](format.md#10-versioning).
