# Roadmap

## Honest assessment (2026-10-12)

- This is a fresh scaffold. Template format v0 is a first draft; no template outside this
  repository has been written against it yet, so expect changes before v1.
- What works: the v0 spec (`docs/format.md`) and JSON Schemas; `validate` with 42
  validation problem codes, each with a fixture that reports exactly that code; `render`
  for all eleven slot types in SQL and Python, including `expressions` for select lists
  and measures; `run_tests` on DuckDB, with SQLGlot transpilation for Databricks,
  Snowflake and Fabric entries; the `emo-template` CLI (`validate`, `new`, `test`); one
  example (`aggregation-gold` on DuckDB with slots `source_table`, `target_table`,
  `group_by`, `measures`; two cases, three runs). The gate runs 336 tests, including
  hypothesis fuzzing of the validator and of SQL rendering.
- What does not exist yet: a PyPI release, a release workflow, examples for the other nine
  shapes or for any production platform, CI on macOS or Windows.
- Local tests prove logic on DuckDB only. Nothing here runs a template on Databricks,
  Snowflake or Fabric, and SQLGlot transpilation has known gaps (see Gaps).

## Current focus

1. Write one template per production platform against v0 (Databricks, Snowflake, Fabric)
   as examples, and fix the format where it gets in the way.
2. Decide the open format questions below that block real templates: platform-only
   statements and Fabric warehouse templates.
3. Publish 0.1.x to PyPI with a tag-driven release workflow.

## Gaps

- No way to mark platform-only statements (`OPTIMIZE`, `VACUUM`, `CLUSTER BY`, table
  properties) so local tests skip them; today such a template fails with
  `transpile-failed`.
- Fabric warehouse (T-SQL) templates cannot be declared; every `fabric` entry is read as
  Spark SQL.
- Python entries for `databricks`, `snowflake` and `fabric` are compiled but never run;
  their test cases are skipped.
- Transpiled date arithmetic (`date_add`, `DATEADD`) returns `TIMESTAMP` on DuckDB and
  shows up as a type mismatch; authors must cast by hand.
- No escape for a literal `{{` in entry files.
- A Snowflake object created with a quoted lower- or mixed-case name cannot be named by a
  slot value; reserved words in `expression` and `expressions` values are the author's to
  quote. Spark's `enforceReservedKeywords` set to `true` is not handled.
- `profile_version`, `requires` and `forbids` are only syntax-checked; there is no
  published list of feature names.
- Floating-point columns compare exactly; there is no tolerance option.
- `emo-template test` runs template SQL and Python with the user's privileges and no
  sandbox; only the docs and `test --help` warn about it.
- The format does not say which slots a shape's templates must declare. The
  `aggregation-gold` example declares `source_table`, `target_table`, `group_by` and
  `measures`; nothing checks other templates against a per-shape list.
- `expressions` items are not checked for duplicate aliases; a duplicate fails only when
  the test runs.
- `validate` reports manifest schema errors without line numbers.
- One example template; none for the other nine shapes.
- No release workflow; not on PyPI.
- CI runs on Linux only.

## Done

- 2026-10-12: scaffold. Format v0 spec and schemas, validator, renderer, DuckDB test
  runner with SQLGlot transpilation, `emo-template` CLI, `aggregation-gold` DuckDB
  example, fixture generator, test suite with fuzzing, CI gate.
- 2026-10-12: slot type `expressions`; per-dialect literal rendering documented and
  tested; `aggregation-gold` example on `group_by` and `measures`; warning that testing
  executes templates.
- 2026-10-25: identifier slot values that the dialect reserves are written quoted, in the
  case the dialect gives the unquoted name (Snowflake's 92 keywords, DuckDB's 75).
