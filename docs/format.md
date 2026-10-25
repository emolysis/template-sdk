# Template format v0

Status: **draft**. This document is normative for templates whose manifest says
`format: emolysis.template/v0`, and for every tool that reads, renders or tests them. The
validator (`emo-template validate`), the renderer and the test runner
(`emo-template test`) in this repository are the reference implementation; where they
disagree with this document, that is a bug in one of them, and this document wins until it
is changed.

The JSON Schemas for the two structured files ship with the package:
[`template.v0.schema.json`](../src/emolysis_template_sdk/schemas/template.v0.schema.json) and
[`profile_constraints.v0.schema.json`](../src/emolysis_template_sdk/schemas/profile_constraints.v0.schema.json).
The schemas cover structure; the rules below that a schema cannot express are checked by
the validator.

## 1. What a template is

A template is a directory that implements one pipeline shape for one platform: an entry
file with slots, notes on what it costs to run, what it needs from the platform, and
golden tests that prove it on DuckDB.

## 2. Directory layout

```
<template-dir>/
  template.yaml              manifest, required
  template.sql | template.py entry file, exactly one, named in manifest.entry
  cost.md                    cost notes for the target platform, required
  profile_constraints.json   required
  tests/
    <case>/
      slots.yaml             slot values for this case, required
      runs/
        01/
          input/<table>.parquet
          expected/<table>.parquet
        02/ ...
```

- File and directory names are case-sensitive.
- Entries whose name starts with `.` (for example `.gitkeep`, `.DS_Store`) are ignored
  everywhere.
- Other files at the template root (a `README.md`, helper notes) are allowed and ignored.
- Files are UTF-8.

## 3. `template.yaml`

### Reading YAML

`template.yaml` and `slots.yaml` are read with YAML core-schema scalars, not YAML 1.1:

- only `true` and `false` (any capitalization of those words) are booleans; `yes`, `no`,
  `on`, `off` are strings;
- integers are decimal (`017` is 17; `0x1F` is a string);
- dates and times (`2026-10-12`, `12:30`) are strings;
- duplicate keys in a mapping are an error.

Quote values when in doubt.

### Fields

| Field         | Type   | Required | Rules                                                     |
| ------------- | ------ | -------- | --------------------------------------------------------- |
| `format`      | string | yes      | exactly `emolysis.template/v0`                             |
| `id`          | string | yes      | `<shape>.<platform>`, for example `scd2.databricks`       |
| `shape`       | string | yes      | a shape id from the table below                           |
| `platform`    | string | yes      | a platform id from the table below                        |
| `version`     | string | yes      | semantic version of this template, for example `0.1.0`    |
| `title`       | string | yes      | 1 to 120 characters                                       |
| `description` | string | yes      | one paragraph, not empty                                  |
| `entry`       | string | yes      | `template.sql` or `template.py`                           |
| `slots`       | list   | yes      | slot declarations (section 4); may be empty               |
| `x-*`         | any    | no       | extension keys; allowed here and in slot entries, ignored |

Any other key is an error. Quote `version` if YAML could read it as a number.

### Shapes

| Id                   | Name               | What the golden tests should cover |
| -------------------- | ------------------ | ---------------------------------- |
| `ingest-batch`       | Ingest (batch)     | 3 files, one malformed             |
| `incremental-append` | Incremental append | two runs, overlap                  |
| `cdc-merge`          | CDC merge          | insert/update/delete mix           |
| `scd2`               | SCD Type 2         | attribute change across 3 runs     |
| `snapshot`           | Snapshot           | two snapshots                      |
| `backfill`           | Backfill           | gap in the middle                  |
| `late-arriving`      | Late-arriving      | fact 2 days late                   |
| `dedupe-conform`     | Dedupe / conform   | duplicates + type drift            |
| `aggregation-gold`   | Aggregation / gold | known totals                       |
| `reverse-etl`        | Reverse ETL        | idempotent push                    |

The test column is guidance for authors; the validator does not check it.

### Platforms

| Id           | Entry is written in (SQLGlot dialect) | Notes                                      |
| ------------ | ------------------------------------- | ------------------------------------------ |
| `databricks` | `databricks`                          | Spark SQL / PySpark on Databricks          |
| `snowflake`  | `snowflake`                           | Snowflake SQL                              |
| `fabric`     | `spark`                               | Fabric lakehouse (Spark SQL / PySpark)     |
| `duckdb`     | `duckdb`                              | local-only templates; no transpile needed |

v0 has no way to declare a Fabric warehouse (T-SQL) template; a `fabric` entry is read as
Spark SQL.

## 4. Slots

A slot is a named hole in the entry file that the caller fills.

```yaml
slots:
  - name: source_table
    type: table
    required: true
    description: Staged changes to apply.
  - name: mode
    type: enum
    enum: [merge, overwrite]
    default: merge
```

| Field         | Rules                                                                    |
| ------------- | ------------------------------------------------------------------------ |
| `name`        | `[a-z][a-z0-9_]*`, at most 64 characters, unique in the template         |
| `type`        | one of the slot types below                                              |
| `required`    | boolean, default `false`                                                 |
| `default`     | value used when none is given; must be valid for `type`                  |
| `description` | string, optional; shown to whoever fills the slot                        |
| `enum`        | list of allowed values; required for `type: enum`, forbidden otherwise   |

- A slot with `required: true` must not have a `default`.
- A slot that is not required must have a `default`. There are no empty optional slots,
  because v0 has no conditionals to leave text out.
- `enum` values match `[A-Za-z_][A-Za-z0-9_]*` and are unique.

### Slot types

| Type          | Value in YAML                                                  | SQL rendering                                                    | Python rendering        |
| ------------- | -------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------- |
| `identifier`  | string matching `[A-Za-z_][A-Za-z0-9_]*`                       | verbatim, or quoted when the dialect reserves it (below)         | string literal          |
| `table`       | 1 to 3 identifiers joined by `.`                               | each part as `identifier`, joined with `.`                       | string literal          |
| `column`      | identifier                                                     | as `identifier`                                                  | string literal          |
| `columns`     | non-empty list of identifiers, unique ignoring case            | each item as `identifier`, joined with `, `                      | list of string literals |
| `expression`  | one SQL expression in the template's dialect                   | verbatim                                                         | string literal          |
| `expressions` | non-empty list of SQL expressions, each with an optional alias | each item rewritten by SQLGlot for the dialect, joined with `, ` | list of string literals |
| `string`      | any string                                                     | string literal, quoted and escaped for the dialect               | string literal          |
| `integer`     | integer (not a boolean)                                        | decimal digits                                                   | decimal digits          |
| `boolean`     | `true` or `false`                                              | `TRUE` / `FALSE`                                                 | `True` / `False`        |
| `duration`    | `<n> <unit>`, for example `2 days`, `15m`                      | interval literal for the dialect                                 | whole seconds (integer) |
| `enum`        | one of the slot's `enum` values                                | verbatim                                                         | string literal          |

Details:

- An `identifier`, `column`, `columns` item or `table` part that the template's dialect
  reserves is written as a quoted identifier naming the same object as the unquoted word
  would; any other is written verbatim. See "Identifiers and reserved words" below.
- `expression` must parse as exactly one SQL expression in the template's dialect
  (section 3, Platforms): no `;`, no top-level query (a scalar subquery must be in
  parentheses), no alias. For a Python entry the check uses the same dialect, since the
  string usually ends up in SQL.
- `expressions` is for select lists and aggregations, for example the measures of an
  aggregate: `[count(*) AS orders, sum(amount) AS revenue]`. Each item is a non-empty
  string that parses, in the template's dialect, as exactly one SQL expression optionally
  followed by an alias (`sum(amount) AS revenue`; `AS` may be left out). Otherwise the
  rules of `expression` apply: no `;`, no top-level query, no other clause (`FROM`,
  `WHERE`, `DISTINCT`, ...). Items are not checked for duplicate aliases.
- In SQL, each `expressions` item is parsed and written back by SQLGlot in the template's
  dialect, and the items are joined with `, `. Keywords and function names come out in
  upper case, comments are dropped, an alias is always written with `AS`, and SQLGlot may
  write a construct in an equivalent form for the dialect (Snowflake has no `FILTER`
  clause, so `count(*) FILTER (WHERE x)` becomes `COUNT_IF(x)`). The rendered text is
  therefore exactly one select-list item per list entry. In Python the value renders as a
  list of the strings as written.
- `duration` units: `s`, `sec`, `second(s)`, `m`, `min`, `minute(s)`, `h`, `hr`,
  `hour(s)`, `d`, `day(s)`, `w`, `week(s)`, any capitalization, amount 0 to 999999999.
- Literals in SQL (`string`, `boolean`, `duration`) are written by SQLGlot for the
  template's dialect, never with one dialect's escaping applied to another. Examples:

  | Value             | `duckdb`           | `databricks`, `spark` (`fabric`) | `snowflake`        |
  | ----------------- | ------------------ | -------------------------------- | ------------------ |
  | string `it's`     | `'it''s'`          | `'it\'s'`                        | `'it\'s'`          |
  | string `a\b`      | `'a\b'`            | `'a\\b'`                         | `'a\\b'`           |
  | duration `2 days` | `INTERVAL '2' DAY` | `INTERVAL '2' DAY`               | `INTERVAL '2 DAY'` |
  | boolean `true`    | `TRUE`             | `TRUE`                           | `TRUE`             |

  A rendered string literal parses back, in its dialect, to exactly the value given.
- Python string literals are Python `repr()` of the value.

### Identifiers and reserved words

A slot value that names a table or a column is written verbatim unless the template's
dialect reserves it. A reserved one is written as a quoted identifier, in the case the
dialect gives the same name unquoted, so the quoted name and the unquoted word name the
same object. The check ignores case: `Order` and `ORDER` are the word `order`.

| Dialect                         | Reserved words                                                              | `order` is written | Lists and rules                                                                |
| ------------------------------- | --------------------------------------------------------------------------- | ------------------ | ------------------------------------------------------------------------------ |
| `snowflake`                     | the 92 keywords of Snowflake's reserved and limited keywords table          | `"ORDER"`          | https://docs.snowflake.com/en/sql-reference/reserved-keywords, read 2026-10-25 |
| `duckdb`                        | the 75 keywords `duckdb_keywords()` puts in the `reserved` category (1.5.6) | `"order"`          | https://duckdb.org/docs/stable/sql/dialect/keywords_and_identifiers            |
| `databricks`                    | none for slot values                                                        | `order`            | https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-reserved-words  |
| `spark` (the `fabric` platform) | none for slot values                                                        | `order`            | https://spark.apache.org/docs/latest/sql-ref-ansi-compliance.html              |

- **Snowflake** stores and resolves an unquoted name in upper case, and a quoted name
  exactly as written
  ([identifier rules](https://docs.snowflake.com/en/sql-reference/identifiers-syntax)). So
  a reserved name is written in upper case: `order`, `Order` and `ORDER` all become
  `"ORDER"`, the column a bare `order` would name if Snowflake allowed it. Examples:
  `group` becomes `"GROUP"`, `start` becomes `"START"`, and the table `analytics.group.orders`
  becomes `analytics."GROUP".orders`.
- **DuckDB** matches names without regard to case, quoted or not
  ([keywords and identifiers](https://duckdb.org/docs/stable/sql/dialect/keywords_and_identifiers)).
  A reserved name keeps the case it was given: `order` becomes `"order"`.
- **Databricks** does not enforce the ANSI reserved words. It needs back-ticks only around a
  few words used as a table alias (`JOIN`, `LEFT`, `ON` and the others its page lists), and
  it keeps some catalog and schema names for its own use, such as `INFORMATION_SCHEMA`
  ([reserved words](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-reserved-words)).
  Slot values are written verbatim. A template that uses an `identifier` slot as a table
  alias must not let it take one of the alias words.
- **Spark**, which `fabric` templates are written in, reserves no word as an identifier
  (a few cannot be a table alias) while `spark.sql.ansi.enforceReservedKeywords` is
  `false`, its default
  ([ANSI compliance](https://spark.apache.org/docs/latest/sql-ref-ansi-compliance.html)).
  Slot values are written verbatim. A session with that setting `true` is outside v0's
  guarantee.
- The lists ship with the SDK; rendering never asks a database. A word on a list that the
  platform would also accept bare still names the same object when quoted, so a list errs
  on the side of quoting.
- Not covered: an `expression` or `expressions` value is written as given or as SQLGlot
  writes it, so a reserved column name inside one must be quoted by whoever writes the
  value, in the dialect's own way. A Snowflake object created with a quoted lower- or
  mixed-case name (`"order"`, `"CustomerID"`) cannot be named by a slot value.

## 5. Entry file and substitution

- Slots are referenced as `{{ slot_name }}`. Spaces or tabs inside the braces are
  optional: `{{name}}` and `{{  name  }}` are the same reference.
- Substitution is textual and happens everywhere in the file, including comments and
  string literals.
- There is no other template syntax: no filters (`{{ x | upper }}`), no expressions, no
  `{% ... %}` blocks and no `{# ... #}` comments. Any `{{` that does not start a valid
  reference, and any `{%` or `{#`, is an error. v0 has no escape for a literal `{{`.
- Every reference must name a declared slot, and every declared slot must be referenced.
- Values resolve as: the value given for the slot, else its `default`. A required slot
  without a value is an error.

### SQL entries (`template.sql`)

Written in the platform's dialect (section 3). One or more statements separated by `;`.

### Python entries (`template.py`)

The rendered file is a Python module. For local tests it must define, at module level, a
function `run(con)` that receives a DuckDB connection. v0 runs Python entries locally
only for platform `duckdb`; for other platforms the validator checks that the rendered
module compiles and the runner skips its tests with a warning.

## 6. `cost.md`

Markdown, not empty. Say what running the template costs on its platform: the compute it
needs, how cost grows with input size, and the settings that change it.

## 7. `profile_constraints.json`

What the template needs from the platform it runs on.

```json
{ "platform": "databricks", "profile_version": ">=1", "requires": ["delta"], "forbids": [] }
```

| Field             | Rules                                                                         |
| ----------------- | ----------------------------------------------------------------------------- |
| `platform`        | a platform id; must equal `platform` in `template.yaml`                        |
| `profile_version` | comma-separated comparisons on an integer: `>=1`, `>=1,<3`; a bare `2` is `==2` |
| `requires`        | features the platform must provide, unique, `[a-z0-9][a-z0-9_-]*`             |
| `forbids`         | features that must not be in use, same rules                                  |

All four fields are required; `requires` and `forbids` may be empty and must not share a
feature. Keys starting with `x-` are allowed and ignored; other keys are errors. Duplicate
keys are an error.

## 8. Tests

### Layout rules

- `tests/` holds at least one case directory. Case names match `[a-z0-9][a-z0-9_-]*`.
  `tests/` and each case directory may also hold `*.md` notes.
- `slots.yaml` is required in every case. It is a mapping from slot name to value; an
  empty file means no values. Keys must be declared slots; values must be valid for the
  slot type; required slots must have a value.
- `runs/` holds at least one run. Runs are directories named with two digits, numbered
  from `01` without gaps.
- Each run has an `input/` and an `expected/` directory and nothing else. `input/` may be
  empty (keep a `.gitkeep` so version control keeps it); `expected/` holds at least one
  table.
- Table files are `<table>.parquet`, where `<table>` matches `[A-Za-z_][A-Za-z0-9_]*`
  and is unique in its directory ignoring case. Nothing else belongs in `input/` or
  `expected/`.

### Running tests executes the template

Testing a template runs its code on your machine with your privileges. Its SQL runs in
DuckDB, which can read and write local files, install and load extensions and, through
them, reach the network; a Python entry runs inside the test process. Run tests only on
templates you trust. Validation never executes a template: it parses rendered SQL with
SQLGlot and compiles rendered Python without running it.

### Run semantics

Each case runs in a fresh in-memory DuckDB database. The runs are applied in order
`01`, `02`, ...; for each run:

1. Every `input/<table>.parquet` is loaded with `CREATE OR REPLACE TABLE <table>`.
   Tables from earlier runs, including the template's own outputs, keep their state.
2. The rendered entry executes:
   - SQL with platform `duckdb` runs as written.
   - SQL for any other platform is transpiled with SQLGlot from the platform's dialect
     to `duckdb`, statement by statement. If a statement cannot be parsed, is only
     understood as an opaque command, or cannot be expressed in DuckDB, the case fails
     with `transpile-failed`.
   - Python calls `run(con)` (platform `duckdb` only).
3. Every `expected/<table>.parquet` is compared with the table `<table>` in DuckDB's
   default schema.

A run that fails stops its case; later runs depend on its state. Cases are independent.

Because outputs are looked up by plain name in the default schema, test cases should give
`table` slots unqualified names.

### Comparison

- Columns are matched by name, ignoring case. Missing or extra columns fail.
- Each column's type must be in the same family as the expected column's type: exact
  numbers (integers and decimals), approximate numbers (`FLOAT`, `DOUBLE`), strings,
  booleans, dates, timestamps, timestamps with time zone, times, intervals, nested types,
  and any other type only with itself. Widths and precision may differ (`INTEGER` matches
  `HUGEINT`; `DECIMAL(18,2)` matches `DECIMAL(38,2)`).
- Rows are compared as multisets (order is ignored, duplicates count) using `EXCEPT ALL`
  in both directions, after DuckDB's implicit cast to a common type. `NULL` equals
  `NULL`.
- Floating-point values are compared exactly; store fractional amounts as `DECIMAL`.

### Transpilation caveats

SQLGlot covers most of what templates use, not everything:

- Date arithmetic can change type. Spark's `date_add` and Snowflake's `DATEADD` on a
  `DATE` become `DATE + INTERVAL` on DuckDB, which returns a `TIMESTAMP`, and the
  comparison then reports a type mismatch. Cast the result explicitly.
- Platform-only statements (`OPTIMIZE`, `VACUUM`, table properties such as
  `CLUSTER BY` on Databricks) cannot run locally, and v0 has no way to mark a statement
  as platform-only.
- An identifier DuckDB reserves is written quoted when a statement is transpiled to DuckDB
  (section 4, "Identifiers and reserved words"), so a column named `group` or `end` that a
  Databricks or Spark template writes bare runs locally too. SQLGlot's DuckDB writer alone
  quotes only some of those words.
- A passing local test shows the logic is right on DuckDB. It does not prove the
  template runs on the platform.

## 9. Problem codes

Every problem has a stable code, a severity, a path relative to the template directory
and, where known, a line. Errors make a template invalid (`emo-template validate` exits 1)
or fail a test case; warnings do not.

| Code | Severity | Stage | Meaning |
| --- | --- | --- | --- |
| `template-dir-missing` | error | validate | the path is not a directory |
| `io-error` | error | validate | a file or directory could not be read |
| `internal` | error | validate | a bug in the validator; please report it |
| `manifest-missing` | error | validate | no `template.yaml` |
| `yaml-invalid` | error | validate | `template.yaml` or `slots.yaml` is not valid YAML (or has duplicate keys) |
| `manifest-invalid` | error | validate | `template.yaml` breaks the schema: missing or unknown field, wrong type, bad pattern |
| `format-unsupported` | error | validate | `format` is not `emolysis.template/v0`; nothing else is checked |
| `shape-unknown` | error | validate | `shape` is not a known shape id |
| `platform-unknown` | error | validate | `platform` is not a known platform id |
| `id-mismatch` | error | validate | `id` is not `<shape>.<platform>` |
| `slot-type-unknown` | error | validate | a slot's `type` is not a known slot type |
| `slot-duplicate` | error | validate | two slots have the same name |
| `slot-enum-invalid` | error | validate | `enum` missing on an enum slot, or present on another type |
| `slot-default-missing` | error | validate | an optional slot has no `default` |
| `slot-default-conflict` | error | validate | a required slot has a `default` |
| `slot-default-invalid` | error | validate | a `default` is not valid for the slot type |
| `entry-missing` | error | validate | the entry file named in the manifest does not exist |
| `entry-ambiguous` | error | validate | both `template.sql` and `template.py` exist |
| `entry-unreadable` | error | validate | the entry file is not UTF-8 |
| `placeholder-invalid` | error | validate | `{{` that is not a slot reference, or `{%` / `{#` |
| `placeholder-undeclared` | error | validate | a reference to a slot the manifest does not declare |
| `slot-unused` | error | validate | a declared slot is never referenced |
| `entry-python-invalid` | error | validate | the rendered Python entry does not compile |
| `entry-sql-unparsable` | warning | validate | SQLGlot cannot parse the rendered SQL in the platform dialect |
| `cost-missing` | error | validate | no `cost.md` |
| `cost-empty` | error | validate | `cost.md` is empty |
| `constraints-missing` | error | validate | no `profile_constraints.json` |
| `constraints-invalid` | error | validate | invalid JSON, schema violation, or a feature both required and forbidden |
| `constraints-platform-mismatch` | error | validate | its `platform` differs from the manifest |
| `tests-missing` | error | validate | no `tests/` or no cases in it |
| `case-name-invalid` | error | validate | a case directory name breaks the naming rule |
| `case-slots-missing` | error | validate | a case has no `slots.yaml` |
| `case-slots-invalid` | error | validate | `slots.yaml` is not a mapping |
| `slot-unknown` | error | validate | a value is given for a slot the template does not declare |
| `slot-missing` | error | validate | a required slot has no value |
| `slot-value-invalid` | error | validate | a value does not fit its slot type |
| `runs-missing` | error | validate | a case has no `runs/` or no runs in it |
| `runs-malformed` | error | validate | a run is not a two-digit directory, or numbering has gaps |
| `run-incomplete` | error | validate | a run lacks `input/` or `expected/`, or `expected/` is empty |
| `file-unexpected` | error | validate | a file where the layout does not allow one |
| `table-name-invalid` | error | validate | a table file name is not an identifier, or repeats ignoring case |
| `parquet-invalid` | error | validate | a `.parquet` file is not Parquet |
| `transpile-failed` | error | test | SQL cannot be transpiled from the platform dialect to DuckDB |
| `run-failed` | error | test | a statement or `run(con)` failed |
| `python-run-missing` | error | test | a Python entry does not define `run(con)` |
| `python-entry-skipped` | warning | test | a Python entry for a platform other than `duckdb`; its cases are skipped |
| `input-unreadable` | error | test | DuckDB cannot read an input or expected Parquet file |
| `table-missing` | error | test | the run did not produce an expected table |
| `columns-mismatch` | error | test | column names or type families differ from the expected table |
| `rows-mismatch` | error | test | rows differ; the message shows up to five of each side |
| `compare-failed` | error | test | the actual and expected values cannot be compared |

## 10. Versioning

- The `format` string names the format version. A reader rejects every format it does
  not know (`format-unsupported`) instead of guessing.
- **v0 is a draft.** It can change in incompatible ways in any SDK release until v1 is
  declared. Every change is listed in the changelog below with the SDK version that
  ships it.
- From v1 on, a format version only gains backward-compatible additions (new optional
  fields, new problem codes, new warnings). Anything that would make a valid template
  invalid, or change what a valid template renders to, needs a new format version with
  its own `format` string and schema files (`template.v1.schema.json`, ...). The SDK
  lists which format versions it reads.
- A template's own `version` is semantic: bump the major version when slot names, types or
  requiredness change or outputs change incompatibly; the minor version for new optional
  slots or new output columns; the patch version for fixes that keep every existing test
  case passing unchanged.
- The SDK package (`emolysis-template-sdk`) has its own semantic version; it is not the
  format version.

## 11. Changelog

| Format | SDK   | Date       | Change                                                                                                                                              |
| ------ | ----- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| v0     | 0.1.0 | 2026-10-12 | First draft.                                                                                                                                        |
| v0     | 0.1.0 | 2026-10-12 | New slot type `expressions` (section 4). Literal rendering per dialect stated with examples (section 4). Testing executes the template (section 8). |
| v0     | 0.1.0 | 2026-10-25 | An identifier slot value that the dialect reserves is written quoted (section 4, "Identifiers and reserved words"). Any other value renders as before. |
| v0     | 0.1.0 | 2026-10-25 | A statement transpiled to DuckDB for a test quotes every identifier DuckDB reserves (section 8). |
